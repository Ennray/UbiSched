//
// Created by zhengyanzhu on 2022/11/7.
//

#include "Utils.h"
#include <iostream>
#include <vector>
#include <cstring>
using namespace std;

#include <fstream>
#include <algorithm>

vector<string> Utils::split(const string& str, const string& delim){
    vector<string> res;
    if("" == str) return res;
    //先将要切割的字符串从string类型转换为char*类型
    char * strs = new char[str.length() + 1] ; //不要忘了
    strcpy(strs, str.c_str());

    char * d = new char[delim.length() + 1];
    strcpy(d, delim.c_str());

    char *p = strtok(strs, d);
    while(p) {
        string s = p; //分割得到的字符串转换为string类型
        res.push_back(s); //存入结果数组
        p = strtok(NULL, d);
    }

    return res;
}

string Utils::getConf(const string& filename, const string& key) {
    ifstream file(filename);
    if (!file.is_open()) {
        cerr << "无法打开配置文件: " << filename << endl;
        return "";
    }

    string line;
    while (getline(file, line)) {
        if (line.empty() || line[0] == '#' || line[0] == '[') continue;
        size_t pos = line.find('=');
        if (pos != string::npos) {
            string k = line.substr(0, pos);
            string v = line.substr(pos + 1);
            // Trim whitespace
            k.erase(0, k.find_first_not_of(" \t\r\n"));
            k.erase(k.find_last_not_of(" \t\r\n") + 1);
            v.erase(0, v.find_first_not_of(" \t\r\n"));
            v.erase(v.find_last_not_of(" \t\r\n") + 1);

            if (k == key) {
                file.close();
                return v;
            }
        }
    }
    file.close();
    return "";
}
