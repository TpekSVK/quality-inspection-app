# app/dev_rtsp_cli.py
import argparse, cv2 as cv, time
from io.cameras.rtsp_camera import RTSPCamera

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="RTSP URL (rtsp://user:pass@ip:554/...)")
    args = ap.parse_args()

    cam = RTSPCamera(args.url)
    cam.open(); cam.start()
    print("RTSP kamera beží. Stlač ESC pre ukončenie.")

    while True:
        frame = cam.get_frame(timeout_ms=500)
        if frame is not None:
            cv.imshow("RTSP", frame)
        k = cv.waitKey(1) & 0xff
        if k == 27:  # ESC
            break

    cam.stop(); cam.close()
    cv.destroyAllWindows()

if __name__ == "__main__":
    main()
