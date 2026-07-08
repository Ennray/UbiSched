# 选择插件集成：
插件接口：SelectAPI.h
```c++
class SelectAPI {
public:
    virtual map<int,int> select(vector<CapabilityCanUse> resourceCapCanUseTB,CapabilityNeed* capNeedTB) = 0;
};
```
插件实现

继承 public PluginImpl<SelectPlugin>, public SelectAPI

```c++
class SelectPlugin : public PluginImpl<SelectPlugin>, public SelectAPI {
public:
    SelectPlugin();
    ~SelectPlugin() {
    }
    map<int,int> select(vector<CapabilityCanUse> resourceCapCanUseTB,CapabilityNeed* capNeedTB);
};
```

选择插件选择算法实现

在派生类中实现select函数 函数中调用实现的选择方法

```c++
map<int,int> SelectPlugin::select(vector<CapabilityCanUse> resourceCapCanUseTB,CapabilityNeed* capNeedTB) {
    for (int i = 0; i < resourceCapCanUseTB.size(); ++i) {
        cout<<resourceCapCanUseTB[i].getId()<<endl;
    }
    map<int, int> test;
    test = MCTSTree::Select(resourceCapCanUseTB, capNeedTB);
    return test;
}
```

