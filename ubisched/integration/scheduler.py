"""服务内的可选自动调度循环。这里只提交指令，不代替执行器报告完成。"""
import threading
import uuid


class SchedulerLoop:
    def __init__(self, coordinator, interval=0.2):
        self.coordinator = coordinator
        self.interval = interval
        self.halt = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ubisched-scheduler", daemon=True)
        self.last_error = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.halt.set(); self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError("scheduler has not stopped; database remains in use")

    def _run(self):
        while not self.halt.is_set():
            try:
                result = self.coordinator.handle({"operation": "schedule", "request_id": uuid.uuid4().hex})
                self.last_error = result.get("error")
            except Exception as exc:
                # Surface unexpected failures; never silently switch policies.
                self.last_error = str(exc)
                print(f"UbiSched scheduler error: {exc}", flush=True)
            self.halt.wait(self.interval)
