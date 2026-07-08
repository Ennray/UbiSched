//
// Created by zhengyanzhu on 2022/11/26.
//
#ifndef DEMOPLUGIN_ASSESSPLUGIN_H
#define DEMOPLUGIN_ASSESSPLUGIN_H

#include "SelectAPI.h"
#include "PluginImpl.h"

#define DEMO_PLUGIN_NAME "selectplugin"

// 功能插件实现类
// 继承PluginImpl的公共接口，将自己作为模板参数传递
// 实现Demo类中定义的接口
class SelectPlugin : public PluginImpl<SelectPlugin>, public SelectAPI {
public:
    SelectPlugin();
    ~SelectPlugin() {
    }
    bool select(
    const vector<vector<float>>& obs,
    const vector<float>& rnn_states,
    const vector<vector<vector<float>>>& available_actions,
    vector<float>& actions0,
    int UAVid
    );
};
#endif //DEMOPLUGIN_ASSESSPLUGIN_H
