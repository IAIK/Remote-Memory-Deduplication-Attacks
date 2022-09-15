import threading


def terminate_capture_thread(capture_thread):
    try:
        capture_thread.stop()
        capture_thread.join(0.5)
        if capture_thread.is_alive():
            capture_thread.kill()
    except Exception as e:
        print(e)
        pass
