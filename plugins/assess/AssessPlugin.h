#ifndef DEMOPLUGIN_ASSESSPLUGIN_H
#define DEMOPLUGIN_ASSESSPLUGIN_H

// 定义插件名称
#include "AssessAPI.h"
#include "PluginImpl.h"

#define DEMO_PLUGIN_NAME "assessplugin"

// 功能插件实现类
// 继承PluginImpl的公共接口，将自己作为模板参数传递
// 实现Demo类中定义的接口
class AssessPlugin : public PluginImpl<AssessPlugin>, public AssessAPI {
public:
    AssessPlugin();
    ~AssessPlugin() {
    }
    bool assess(vector<Capability*> &capabilities,Environment* curEnv);
};
#endif //DEMOPLUGIN_ASSESSPLUGIN_H
