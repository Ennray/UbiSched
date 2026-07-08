//
// Created by zhengyanzhu on 2022/11/10.
//

#include "PluginMgr.h"
#include "PluginMgrImpl.h"

PluginMgr *PluginMgr::GetInstance() {
    static PluginMgrImpl pmi;
    return &pmi;
}