//
// Created by zhengyanzhu on 2022/11/26.
//

#ifndef SELECT_PLUGINIMPL_H
#define SELECT_PLUGINIMPL_H


#include <string>
#include <memory>

//定义插件的公共接口
class Plugin {
public:
    virtual std::string GetName() = 0;
    virtual int GetVersion() = 0;
    virtual int GetType() = 0;
};

// 被所有的功能插件继承
template <class T> class PluginImpl : public Plugin {
public:
    virtual ~PluginImpl() {
    }
    PluginImpl(std::string name, int version, int type)
            : name_(name), version_(version), type_(type) {
    }
    // 静态函数便于于获取函数地址
    // 模板参数T既是功能插件的实现类
    static std::shared_ptr<Plugin> GetPlugin() {
        std::shared_ptr<Plugin> p = std::make_shared<T>();
        return p;
    }

    // 实现插件公共接口
    std::string GetName() {
        return name_;
    }

    // 实现插件公共接口
    int GetVersion() {
        return version_;
    }

    // 实现插件公共接口
    int GetType() {
        return type_;
    }

private:
    std::string name_;
    int version_;
    int type_;
};

typedef std::shared_ptr<Plugin> (*GetPluginFunction)();
typedef GetPluginFunction (*InitPluginFunction)();

// 每个插件都需要包含InitPlugin这个symbol作为插件的初始化接口
// 告知编译器是C接口，不进行C++的name managling
// 初始化接口返回获取插件实例的接口
// pluginName是功能插件实现类的名称
#define PLUGIN_INIT_FUNCTION_NAME "InitPlugin"
#define DEFINE_PLUGIN(pluginName)                                              \
  extern "C" {                                                                 \
  GetPluginFunction InitPlugin() {                                             \
    return pluginName::GetPlugin;                                              \
  }                                                                            \
  }


#endif //IROS_PLUGINIMPL_H
