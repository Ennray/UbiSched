//
// Created by zhengyanzhu on 2022/11/10.
//

#ifndef IROS_PLUGINMGRIMPL_H
#define IROS_PLUGINMGRIMPL_H


#include "PluginMgr.h"

class PluginMgrImpl : public PluginMgr {
public:
    PluginHandler LoadLibrary(std::string plugin);
    void *GetSymbolAddress(PluginHandler pluginHandler, std::string symbolName);
    void UnloadLibrary(PluginHandler pluginHandler);
};


#endif //IROS_PLUGINMGRIMPL_H
