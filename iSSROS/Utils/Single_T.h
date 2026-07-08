//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_SINGLE_T_H
#define IROS_SINGLE_T_H

#include <iostream>
#include <memory>
#include <mutex>

using namespace std;

//自己加的，泛型删除器
template <typename T>
class SafeDeletor_T{
public:
    void operator()(T *sf)
    {
//        cout << "this is safe deleter operator()" << endl;
        delete sf;
    }
};

template <typename T>
class Single_T {
protected:
    Single_T() = default;
    Single_T(const Single_T<T> &st) = delete;
    Single_T &operator=(const Single_T<T> &st) = delete;
    ~Single_T(){
//        cout << "this is auto safe template destruct" << endl;
    }
public:
    static std::shared_ptr<T> GetInst()
    {
        if (single != nullptr)
        {
            return single;
        }
        s_mutex.lock();
        if (single != nullptr)
        {
            s_mutex.unlock();
            return single;
        }
        //额外指定删除器
        single = std::shared_ptr<T>(new T, SafeDeletor_T<T>());
        //也可以指定删除函数
        // single = std::shared_ptr<SingleAutoSafe>(new SingleAutoSafe, SafeDelFunc);
        s_mutex.unlock();
        return single;
    }
private:
    static std::shared_ptr<T> single;
    static mutex s_mutex;
};



//模板类的static成员要放在h文件里初始化
template <typename T>
std::shared_ptr<T> Single_T<T>::single = nullptr;
template <typename T>
mutex Single_T<T>::s_mutex;

#endif //IROS_SINGLE_T_H
