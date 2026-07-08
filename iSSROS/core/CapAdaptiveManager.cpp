#include "CapAdaptiveManager.h"

#include <iostream>
#include <map>
#include <memory>
#include <unistd.h>
#include <vector>

#include "../Cap/CapabilityAllocated.h"
#include "../Cap/CapabilityCanUse.h"
#include "../core/CapNeedManager.h"
#include "../plugin/AssessAPI.h"
#include "../plugin/PluginImpl.h"
#include "../plugin/PluginMgr.h"
#include "../plugin/SelectAPI.h"

extern string obs0;

void CapAdaptiveManager::run() {
    cout << "run" << endl;

    auto CNM = CapNeedManager::GetInst();
    if (!CNM->isBuild()) {
        cerr << "capNeedTB is not built" << endl;
        return;
    }

    auto pm = PluginMgr::GetInstance();

    vector<string> assessSearchPaths = {
        "libAssessPlugin.so",
        "./libAssessPlugin.so",
        "../libAssessPlugin.so",
        "./plugins/assess/build/libAssessPlugin.so",
        "../plugins/assess/build/libAssessPlugin.so"
    };

    PluginHandler assessHandler = NULL;
    for (const auto& path : assessSearchPaths) {
        assessHandler = pm->LoadLibrary(path.c_str());
        if (assessHandler) {
            printf("[Success] Assess Plugin loaded from: %s\n\r", path.c_str());
            break;
        }
    }

    if (assessHandler) {
        InitPluginFunction init = (InitPluginFunction)pm->GetSymbolAddress(
            assessHandler, PLUGIN_INIT_FUNCTION_NAME);
        if (init) {
            GetPluginFunction get = init();
            if (get) {
                shared_ptr<Plugin> assessPlug = get();
                bool res = dynamic_pointer_cast<AssessAPI>(assessPlug)->assess(resourceCapTB, curEnv);
                cout << "[RuntimeAssess] plugin result: "
                     << (res ? "success" : "failed") << endl;
            } else {
                cout << "[RuntimeAssess] failed: init() returned NULL" << endl;
            }
        } else {
            cout << "[RuntimeAssess] failed: cannot find plugin init symbol" << endl;
        }
    } else {
        printf("[Warning] Failed to load libAssessPlugin.so. Checked paths:\n\r");
        for (const auto& p : assessSearchPaths) printf("  - %s\n\r", p.c_str());
    }

    vector<string> selectSearchPaths = {
        "libselect.so",
        "./libselect.so",
        "../libselect.so",
        "./plugins/select/build/libselect.so",
        "../plugins/select/build/libselect.so"
    };

    PluginHandler selectHandler = NULL;
    for (const auto& path : selectSearchPaths) {
        selectHandler = pm->LoadLibrary(path.c_str());
        if (selectHandler) {
            printf("[Success] Select Plugin loaded from: %s\n\r", path.c_str());
            break;
        }
    }

    if (!selectHandler) {
        printf("[Error] Failed to load libselect.so. Tried paths:\n\r");
        for (const auto& path : selectSearchPaths) {
            printf("  - %s\n\r", path.c_str());
        }
        return;
    }

    InitPluginFunction init = (InitPluginFunction)pm->GetSymbolAddress(
        selectHandler, PLUGIN_INIT_FUNCTION_NAME);
    if (!init) {
        printf("NOT get %s() from .so\n\r", PLUGIN_INIT_FUNCTION_NAME);
        return;
    }

    GetPluginFunction get = init();
    if (!get) {
        printf("select plugin init() failed\n\r");
        return;
    }

    shared_ptr<Plugin> plug = get();
    printf("plugname is %s version is %d type is %d\n\r",
           plug->GetName().c_str(), plug->GetVersion(), plug->GetType());

    cout << "obs:" << obs0 << endl;
    vector<vector<float>> obs;
    obs.push_back(vector<float>());
    for (int i = 0; i < obs0.length(); i++) {
        obs[0].push_back(obs0[i] - '0');
        cout << obs[0][i];
    }
    cout << endl;

    vector<float> rnn_states(64, 0.0);
    vector<vector<vector<float>>> available_actions;
    vector<vector<float>> a;
    vector<float> tasks;
    for (int i = 1; i < obs0.length(); i++) {
        if (obs0[i] == '0') tasks.push_back(0);
        else tasks.push_back(1);
        cout << tasks[i - 1];
    }

    vector<float> sensors = {1, 1, 1, 0};
    available_actions.push_back(a);
    available_actions[0].push_back(tasks);
    available_actions[0].push_back(sensors);

    vector<float> actions0;
    extern int UAVid;
    bool success = dynamic_pointer_cast<SelectAPI>(plug)->select(
        obs, rnn_states, available_actions, actions0, UAVid);

    if (success) {
        cout << "select success" << endl;
        if (!actions0.empty()) {
            map<int, int> res;
            res[(int)actions0[0]] = (int)actions0[1];
            cout << "cont: " << (int)actions0[0] << ' ' << res[(int)actions0[0]] << endl;
            resourceCapAllocatedTB = new CapabilityAllocated(res);
        }
    } else {
        cout << "select failed" << endl;
    }
}
