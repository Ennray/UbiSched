"""状态生产端接口，以及旧评估分值到新版质量字段的显式转换。"""
from ubisched.integration.snapshot import identifier, number


def assessment_patch(report):
    """旧评估按探测、识别、测距返回三个值。调用方必须指定采用哪个指标。

    转换只归一化已得到的评估结果，不在这里另造天气影响公式。
    """
    rid = identifier(report.get("resource_id"), "resource_id")
    modality = identifier(report.get("modality"), "modality")
    metric = report.get("metric")
    if metric not in {"detection", "recognition", "ranging"}:
        raise ValueError("assessment metric must be detection/recognition/ranging")
    scores = report.get("scores")
    if not isinstance(scores, list) or len(scores) != 3:
        raise ValueError("assessment scores must contain three values")
    scale = number(report.get("scale", 100), "assessment scale", minimum=0.001)
    values = [number(v, "assessment score", maximum=scale)/scale for v in scores]
    return {"resource_id": rid, "sensing_quality": {
        modality: values[{"detection": 0, "recognition": 1, "ranging": 2}[metric]]}}


class TelemetryProducer:
    """真实采集端或测试采集端共用的客户端；时间单位为任务开始后的秒数。"""
    def __init__(self, client):
        self.client = client

    def initialize(self, snapshot, request_id):
        return self.client.call("initialize", request_id=request_id, snapshot=snapshot)

    def publish(self, *, request_id, expected_revision, at, resources=(), links=(), assessments=()):
        return self.client.call("telemetry", request_id=request_id, expected_revision=expected_revision,
                                at=at, resources=list(resources), links=list(links), assessments=list(assessments))
