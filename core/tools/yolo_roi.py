# core/tools/yolo_roi.py
import numpy as np
import cv2 as cv
from typing import Dict, Tuple, Optional, List, Any
from .base_tool import BaseTool, ToolResult

try:
    import onnxruntime as ort
except Exception:
    ort = None  # umožní import projektu bez ORT (na dev PC doplníš pip)

def _warp_roi(img: np.ndarray, H: Optional[np.ndarray], roi: Tuple[int,int,int,int]) -> np.ndarray:
    x, y, w, h = roi
    if H is not None:
        warped = cv.warpPerspective(img, H, (img.shape[1], img.shape[0]))
        return warped[y:y+h, x:x+w]
    else:
        return img[y:y+h, x:x+w]

def _letterbox(im, new_shape=(640, 640), stride=32):
    # zachová pomer strán, doplní okraje
    shape = im.shape[:2]  # h, w
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    dw /= 2; dh /= 2

    if shape[::-1] != new_unpad:
        im = cv.resize(im, new_unpad, interpolation=cv.INTER_LINEAR)
    top, bottom = int(round(dh-0.1)), int(round(dh+0.1))
    left, right = int(round(dw-0.1)), int(round(dw+0.1))
    im = cv.copyMakeBorder(im, top, bottom, left, right, cv.BORDER_CONSTANT, value=(114,114,114))
    return im, r, (dw, dh)

def _nms(boxes, scores, iou_th=0.45):
    idxs = scores.argsort()[::-1]
    keep = []
    while idxs.size > 0:
        i = idxs[0]
        keep.append(i)
        if idxs.size == 1:
            break
        xx1 = np.maximum(boxes[i,0], boxes[idxs[1:],0])
        yy1 = np.maximum(boxes[i,1], boxes[idxs[1:],1])
        xx2 = np.minimum(boxes[i,2], boxes[idxs[1:],2])
        yy2 = np.minimum(boxes[i,3], boxes[idxs[1:],3])

        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        inter = w*h
        union = (boxes[i,2]-boxes[i,0])*(boxes[i,3]-boxes[i,1]) + (boxes[idxs[1:],2]-boxes[idxs[1:],0])*(boxes[idxs[1:],3]-boxes[idxs[1:],1]) - inter
        iou = inter / (union + 1e-6)
        idxs = idxs[1:][iou <= iou_th]
    return keep

class YOLOModel:
    def __init__(self, onnx_path: str, providers: Optional[List[str]] = None):
        if ort is None:
            raise ImportError("onnxruntime nie je nainštalované. pip install onnxruntime-gpu (alebo onnxruntime)")
        prov = providers or (['TensorrtExecutionProvider','CUDAExecutionProvider','CPUExecutionProvider'])
        self.session = ort.InferenceSession(onnx_path, providers=prov)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.input_shape = tuple(inp.shape)  # (N, 3, H, W)
        _, _, self.in_h, self.in_w = self.input_shape
        self.out_names = [o.name for o in self.session.get_outputs()]

    def infer(self, img_bgr: np.ndarray) -> np.ndarray:
        # očakáva BGR ROI (H,W,3)
        im = img_bgr
        im_lb, r, (dw, dh) = _letterbox(im, new_shape=(self.in_w, self.in_h))
        im_lb = im_lb[:, :, ::-1]  # BGR->RGB
        im_lb = im_lb.astype(np.float32) / 255.0
        im_lb = np.transpose(im_lb, (2, 0, 1))[None, ...]  # (1,3,H,W)

        outputs = self.session.run(self.out_names, {self.input_name: im_lb})
        # predpoklad: výstup tvar (1, N, 85) [x,y,w,h,conf,cls...]
        preds = outputs[0]
        if isinstance(preds, list): preds = preds[0]
        preds = np.squeeze(preds, axis=0)

        boxes_xywh = preds[:, :4]
        scores = preds[:, 4]
        cls_probs = preds[:, 5:]
        cls_ids = np.argmax(cls_probs, axis=1)
        cls_scores = scores * cls_probs[np.arange(cls_probs.shape[0]), cls_ids]

        # prepočet späť na ROI koordináty
        # xywh -> xyxy
        xy = boxes_xywh[:, :2]
        wh = boxes_xywh[:, 2:4]
        xyxy = np.concatenate([xy - wh/2, xy + wh/2], axis=1)

        # undo letterbox scaling
        gain = min(self.in_w / im.shape[1], self.in_h / im.shape[0])
        pad = np.array([dw, dh, dw, dh])
        xyxy -= pad
        xyxy /= gain
        return xyxy, cls_ids, cls_scores

class YOLOInROITool(BaseTool):
    """
    params:
      - onnx_path: str
      - conf_th: float (napr. 0.25)
      - iou_th: float (napr. 0.45)
      - measure: "count"|"max_conf"|"mean_conf"
      - class_whitelist: Optional[List[int]] (ak chceš filtrovať triedy)
    """
    _model_cache: Dict[str, YOLOModel] = {}

    def _get_model(self, onnx_path: str) -> YOLOModel:
        if onnx_path not in self._model_cache:
            self._model_cache[onnx_path] = YOLOModel(onnx_path)
        return self._model_cache[onnx_path]

    def run(self, img_ref: np.ndarray, img_cur: np.ndarray, fixture_transform: Optional[np.ndarray]) -> ToolResult:
        onnx_path = self.params["onnx_path"]
        conf_th = float(self.params.get("conf_th", 0.25))
        iou_th = float(self.params.get("iou_th", 0.45))
        measure_mode = self.params.get("measure", "count")
        class_whitelist = self.params.get("class_whitelist", None)

        x, y, w, h = self.roi_xywh
        roi = _warp_roi(img_cur, fixture_transform, (x,y,w,h))
        if roi.ndim == 2:
            roi = cv.cvtColor(roi, cv.COLOR_GRAY2BGR)

        model = self._get_model(onnx_path)
        boxes, cls_ids, cls_scores = model.infer(roi)

        # filter conf + classes
        keep = cls_scores >= conf_th
        if class_whitelist is not None:
            keep = keep & np.isin(cls_ids, np.array(class_whitelist))
        boxes, cls_ids, cls_scores = boxes[keep], cls_ids[keep], cls_scores[keep]

        # NMS
        if boxes.shape[0] > 0:
            keep_idx = _nms(boxes, cls_scores, iou_th=iou_th)
            boxes, cls_ids, cls_scores = boxes[keep_idx], cls_ids[keep_idx], cls_scores[keep_idx]

        # measured
        if boxes.shape[0] > 0:
                # jednoduché NMS
                idxs = cls_scores.argsort()[::-1]
                keep_idx = []
                while idxs.size > 0:
                    i = idxs[0]; keep_idx.append(i)
                    if idxs.size == 1: break
                    xx1 = np.maximum(boxes[i,0], boxes[idxs[1:],0])
                    yy1 = np.maximum(boxes[i,1], boxes[idxs[1:],1])
                    xx2 = np.minimum(boxes[i,2], boxes[idxs[1:],2])
                    yy2 = np.minimum(boxes[i,3], boxes[idxs[1:],3])
                    w_ = np.maximum(0, xx2-xx1); h_ = np.maximum(0, yy2-yy1)
                    inter = w_*h_
                    union = (boxes[i,2]-boxes[i,0])*(boxes[i,3]-boxes[i,1]) + (boxes[idxs[1:],2]-boxes[idxs[1:],0])*(boxes[idxs[1:],3]-boxes[idxs[1:],1]) - inter
                    iou = inter / (union + 1e-6)
                    idxs = idxs[1:][iou <= iou_th]
                boxes, cls_ids, cls_scores = boxes[keep_idx], cls_ids[keep_idx], cls_scores[keep_idx]

                if boxes.shape[0] == 0:
                    measured = 0.0 if measure_mode == "count" else 0.0
                else:
                    if measure_mode == "count":
                        measured = float(boxes.shape[0])
                    elif measure_mode == "max_conf":
                        measured = float(cls_scores.max())
                    else:
                        measured = float(cls_scores.mean())

                lsl, usl = self.lsl, self.usl
                ok = True
                if lsl is not None and measured < lsl: ok = False
                if usl is not None and measured > usl: ok = False

                overlay = roi.copy()
                for b, cid, sc in zip(boxes.astype(int), cls_ids, cls_scores):
                    cv.rectangle(overlay, (b[0], b[1]), (b[2], b[3]), (0,255,0) if ok else (0,0,255), 2)
                    cv.putText(overlay, f"{cid}:{sc:.2f}", (b[0], max(0, b[1]-5)), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

                details = {
                    "roi_xywh": (x,y,w,h),
                    "detections": int(boxes.shape[0]),
                    "classes": cls_ids.tolist() if boxes.shape[0] else [],
                    "scores": cls_scores.tolist() if boxes.shape[0] else []
                }
                return ToolResult(ok=ok, measured=measured, lsl=lsl, usl=usl, details=details, overlay=overlay)