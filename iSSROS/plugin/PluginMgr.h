//
// Created by zhengyanzhu on 2022/11/10.
//

#ifndef IROS_PLUGINMGR_H
#define IROS_PLUGINMGR_H

#include <string>

typedef void *PluginHandler;

// 定义插件管理类接口
// 实现单例的GetInstance接口
class PluginMgr {
public:
    static PluginMgr *GetInstance();
    virtual PluginHandler LoadLibrary(std::string plugin) = 0;
    virtual void *GetSymbolAddress(PluginHandler pluginHandler,
                                   std::string symbolName) = 0;
    virtual void UnloadLibrary(PluginHandler pluginHandler) = 0;
};


#endif //IROS_PLUGINMGR_H
