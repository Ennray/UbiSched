#include "AssessPlugin.h"

#include <Python.h>
#include <iostream>
#include <map>
#include <vector>

DEFINE_PLUGIN(AssessPlugin)

using namespace std;

AssessPlugin::AssessPlugin() : PluginImpl(DEMO_PLUGIN_NAME, 1, 1) {
}

bool AssessPlugin::assess(vector<Capability*> &capabilities, Environment* curEnv) {
    if (curEnv == NULL) {
        cout << "[RuntimeAssess] skipped: current environment is NULL" << endl;
        return false;
    }

    cout << "========== Runtime Capability Assessment ==========" << endl;
    cout << "[RuntimeAssess] input "
         << "light=" << curEnv->getLight()
         << ", fog=" << curEnv->getWeather().getFog()
         << ", rain=" << curEnv->getWeather().getRain()
         << ", dust=" << curEnv->getWeather().getDust()
         << endl;

    map<string, string> models;
    models["RGBCap1"] = "eoAssess";
    models["IRCap1"] = "irAssess";
    models["RGBCap2"] = "eoAssess";
    models["IRCap2"] = "irAssess";
    models["IRCap"] = "irAssess";
    models["RGBCap"] = "eoAssess";
    models["EOCap"] = "eoAssess";

    Py_Initialize();
    if (!Py_IsInitialized()) {
        cout << "[RuntimeAssess] error: Py_Initialize failed" << endl;
        return false;
    }

    PyRun_SimpleString("import os");
    PyRun_SimpleString("import sys");
    PyRun_SimpleString("sys.path.append(os.path.abspath('.'))");
    PyRun_SimpleString("sys.path.append(os.path.abspath('..'))");
    PyRun_SimpleString("sys.path.append(os.path.abspath('./iSSROS'))");
    PyRun_SimpleString("sys.path.append(os.path.abspath('../iSSROS'))");
    PyRun_SimpleString("sys.path.append(os.path.abspath('../../iSSROS'))");

    PyObject* pModule = PyImport_ImportModule("assessment");
    if (pModule == NULL) {
        PyErr_Print();
        cout << "[RuntimeAssess] error: cannot import assessment.py" << endl;
        return false;
    }

    for (int i = 0; i < capabilities.size(); ++i) {
        Capability* cur = capabilities[i];
        if (cur == NULL) {
            continue;
        }

        if (!cur->isStatus()) {
            cout << "[RuntimeAssess] resource=" << cur->getVehicleName()
                 << "/" << cur->getName()
                 << " status=offline, skipped" << endl;
            continue;
        }

        if (models.find(cur->getName()) == models.end()) {
            cout << "[RuntimeAssess] resource=" << cur->getVehicleName()
                 << "/" << cur->getName()
                 << " model=unsupported, skipped" << endl;
            continue;
        }

        const char* funcName = models[cur->getName()].c_str();
        PyObject* pFunc = PyObject_GetAttrString(pModule, funcName);
        if (pFunc == NULL || !PyCallable_Check(pFunc)) {
            PyErr_Print();
            cout << "[RuntimeAssess] error: function " << funcName
                 << " not found in assessment.py" << endl;
            Py_XDECREF(pFunc);
            Py_DECREF(pModule);
            return false;
        }

        PyObject* pArgs = PyTuple_New(4);
        PyTuple_SetItem(pArgs, 0, Py_BuildValue("f", curEnv->getLight()));
        PyTuple_SetItem(pArgs, 1, Py_BuildValue("f", curEnv->getWeather().getFog()));
        PyTuple_SetItem(pArgs, 2, Py_BuildValue("f", curEnv->getWeather().getRain()));
        PyTuple_SetItem(pArgs, 3, Py_BuildValue("f", curEnv->getWeather().getDust()));

        PyObject* pRet = PyObject_CallObject(pFunc, pArgs);
        Py_DECREF(pArgs);
        Py_DECREF(pFunc);

        if (pRet == NULL) {
            PyErr_Print();
            cout << "[RuntimeAssess] error: call " << funcName << " failed" << endl;
            Py_DECREF(pModule);
            return false;
        }

        vector<float> assessedValues;
        vector<float> level = cur->getLevel();
        int size = PyList_Size(pRet);
        for (int j = 0; j < size; ++j) {
            PyObject* pResVal = PyList_GetItem(pRet, j);
            float v = 0.0;
            PyArg_Parse(pResVal, "f", &v);
            assessedValues.push_back(v);
            level.push_back(v);
        }
        Py_DECREF(pRet);
        cur->setLevel(level);

        cout << "[RuntimeAssess] resource=" << cur->getVehicleName()
             << "/" << cur->getName()
             << " function=" << funcName
             << " result=[";
        for (int j = 0; j < assessedValues.size(); ++j) {
            if (j > 0) cout << ", ";
            cout << assessedValues[j];
        }
        cout << "] merged_level=[";
        const vector<float>& mergedLevel = cur->getLevel();
        for (int j = 0; j < mergedLevel.size(); ++j) {
            if (j > 0) cout << ", ";
            cout << mergedLevel[j];
        }
        cout << "]" << endl;
    }

    Py_DECREF(pModule);
    cout << "========== Runtime Capability Assessment Done ==========" << endl;
    return true;
}
