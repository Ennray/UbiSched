#include <Python.h>
#include <vector>
#include <iostream>
#include "selectPlugin.h"
using namespace std;
DEFINE_PLUGIN(SelectPlugin)
SelectPlugin::SelectPlugin():PluginImpl(DEMO_PLUGIN_NAME,1,1)
{

}
// 调用actor_inference函数并返回结果
bool SelectPlugin::select(
    const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    int UAVid
) {
    // 初始化Python解释器
    
        Py_Initialize();
        if (!Py_IsInitialized()) {
            cerr << "Python初始化失败" << endl;
            return false;
        }
    

    PyObject *pModule = nullptr, *pFunc = nullptr;
    PyObject *pArgs = nullptr, *pResult = nullptr;

    try {
        // 设置Python路径（根据实际项目路径调整）
        PyRun_SimpleString("import sys");
        PyRun_SimpleString("import os");
        PyRun_SimpleString("sys.path.append(os.path.abspath('./light_mappo-transformer/light_mappo-main'))");
        PyRun_SimpleString("sys.path.append(os.path.abspath('./light_mappo-transformer/light_mappo-main/train'))");
        PyRun_SimpleString("sys.path.append(os.path.abspath('../light_mappo-transformer/light_mappo-main'))");
        PyRun_SimpleString("sys.path.append(os.path.abspath('../light_mappo-transformer/light_mappo-main/train'))");
        PyRun_SimpleString("sys.path.append(os.path.abspath('../../light_mappo-transformer/light_mappo-main'))");
        PyRun_SimpleString("sys.path.append(os.path.abspath('../../light_mappo-transformer/light_mappo-main/train'))");
        PyRun_SimpleString("print('Python Executable:', sys.executable)");
        // 导入包含actor_inference的模块
        pModule = PyImport_ImportModule("new");  // CMTS2 Python文件
        if (!pModule) {
            PyErr_Print();
            throw runtime_error("无法导入Python模块");
        }

        // 获取actor_inference函数
        pFunc = PyObject_GetAttrString(pModule, "actor_inference");
        if (!pFunc || !PyCallable_Check(pFunc)) {
            PyErr_Print();
            throw runtime_error("未找到可调用的actor_inference函数");
        }

        // 1. 构造obs参数（二维列表：[[1,0,0,...], ...]）
        PyObject* py_obs = PyList_New(obs.size());
        for (size_t i = 0; i < obs.size(); ++i) {
            PyObject* py_obs_row = PyList_New(obs[i].size());
            for (size_t j = 0; j < obs[i].size(); ++j) {
                PyList_SetItem(py_obs_row, j, PyFloat_FromDouble(obs[i][j]));
            }
            PyList_SetItem(py_obs, i, py_obs_row);
        }

        // 2. 构造rnn_states参数（一维数组：[0,0,...,0]）
        PyObject* py_rnn = PyList_New(rnn_states.size());
        for (size_t i = 0; i < rnn_states.size(); ++i) {
            PyList_SetItem(py_rnn, i, PyFloat_FromDouble(rnn_states[i]));
        }

        // 3. 构造available_actions参数（三维列表：[[[1,0,...], [1,1,...]], ...]）
        PyObject* py_actions = PyList_New(available_actions.size());
        for (size_t i = 0; i < available_actions.size(); ++i) {
            PyObject* py_actions_agent = PyList_New(available_actions[i].size());
            for (size_t j = 0; j < available_actions[i].size(); ++j) {
                PyObject* py_actions_dim = PyList_New(available_actions[i][j].size());
                for (size_t k = 0; k < available_actions[i][j].size(); ++k) {
                    PyList_SetItem(py_actions_dim, k, PyFloat_FromDouble(available_actions[i][j][k]));
                }
                PyList_SetItem(py_actions_agent, j, py_actions_dim);
            }
            PyList_SetItem(py_actions, i, py_actions_agent);
        }

        // 打包所有参数为元组 (obs, rnn_states, available_actions)
        pArgs = PyTuple_New(4);
        PyTuple_SetItem(pArgs, 0, py_obs);       // 参数1：obs
        PyTuple_SetItem(pArgs, 1, py_rnn);       // 参数2：rnn_states
        PyTuple_SetItem(pArgs, 2, py_actions);   // 参数3：available_actions
        PyTuple_SetItem(pArgs, 3, PyLong_FromLong(UAVid));         // 参数4：UAVid

        // 调用函数
        pResult = PyObject_CallObject(pFunc, pArgs);
        if (!pResult) {
            PyErr_Print();
            throw runtime_error("调用actor_inference失败");
        }
        cout<<"cut1"<<endl;
        // 解析agent0的动作
        if (!PyList_Check(pResult)) {
            throw runtime_error("agent0动作不是列表");
        }
        for (Py_ssize_t i = 0; i < PyList_Size(pResult); ++i) {
            PyObject* item = PyList_GetItem(pResult, i);
            actions0.push_back((float)PyFloat_AsDouble(item));
        }
        cout<<"cut2"<<endl;
    } catch (const exception& e) {
        cerr << "错误: " << e.what() << endl;
        return false;
    }

    // 释放资源
    if (pResult) Py_DECREF(pResult);
    if (pArgs) Py_DECREF(pArgs);   // 包含py_obs, py_rnn, py_actions，无需单独释放
    if (pFunc) Py_DECREF(pFunc);
    if (pModule) Py_DECREF(pModule);
    cout<<"cut3"<<endl;
    return true;
}