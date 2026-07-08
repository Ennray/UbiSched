import os

import numpy as np


def _clip(value):
    return float(max(0.0, min(100.0, value)))


def _load_model_result(model_name, light, fog, rain):
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", model_name))
    if not os.path.exists(model_path):
        return None

    import joblib

    xtest = np.array([rain, fog, light]).reshape(1, 3, 1)
    loaded_model = joblib.load(model_path)
    y_predict = loaded_model.predict(xtest)
    return np.array(y_predict).reshape(1, 3).tolist()[0]


def eoAssess(light, fog, rain, dust):
    model_result = _load_model_result("eomodel.dat", light, fog, rain)
    if model_result is not None:
        return model_result

    detection = _clip(35.0 + 55.0 * light - 45.0 * fog - 25.0 * rain - 20.0 * dust)
    recognition = _clip(30.0 + 50.0 * light - 35.0 * fog - 20.0 * rain - 15.0 * dust)
    ranging = _clip(45.0 + 20.0 * light - 20.0 * fog - 15.0 * rain - 15.0 * dust)
    return [detection, recognition, ranging]


def irAssess(light, fog, rain, dust):
    model_result = _load_model_result("irmodel.dat", light, fog, rain)
    if model_result is not None:
        return model_result

    detection = _clip(55.0 + 10.0 * light - 15.0 * fog - 10.0 * rain - 8.0 * dust)
    recognition = _clip(50.0 + 8.0 * light - 12.0 * fog - 8.0 * rain - 8.0 * dust)
    ranging = _clip(40.0 + 5.0 * light - 10.0 * fog - 8.0 * rain - 8.0 * dust)
    return [detection, recognition, ranging]


if __name__ == "__main__":
    print("EO:", eoAssess(0.8, 0.1, 0.0, 0.0))
    print("IR:", irAssess(0.8, 0.1, 0.0, 0.0))
