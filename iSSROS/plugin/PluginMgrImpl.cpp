//
// Created by zhengyanzhu on 2022/11/10.
//

#include <dlfcn.h>
#include "PluginMgrImpl.h"

PluginHandler PluginMgrImpl::LoadLibrary(std::string plugin) {
    return dlopen(plugin.c_str(), RTLD_LAZY);
}
void *PluginMgrImpl::GetSymbolAddress(PluginHandler pluginHandler,
                                      std::string symbolName) {
    return dlsym(pluginHandler, symbolName.c_str());
}
void PluginMgrImpl::UnloadLibrary(PluginHandler pluginHandler) {
    dlclose(pluginHandler);
}
