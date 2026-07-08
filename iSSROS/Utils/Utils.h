//
// Created by zhengyanzhu on 2022/11/7.
//

#ifndef IROS_UTILS_H
#define IROS_UTILS_H

#include "../Cap/Capability.h"
#include "Single_T.h"
#include <vector>

class Utils : public Single_T<Utils>{
private:
    Utils() = default;
    Utils(const Utils&) = delete;
    Utils & operator=(const Utils &) = delete;
    ~Utils() = default;
    friend class SafeDeletor_T<Utils>;
    friend class Single_T<Utils>;

public:
    vector<string> split(const string& str, const string& delim);
    string getConf(const string& filename, const string& key);
};


#endif //IROS_UTILS_H
