//
// Created by zhengyanzhu on 2022/11/7.
//

#include "CapInterfaceManager.h"
#include "../Utils/Utils.h"
#include <fstream>   // 用于文件操作
#include <sstream>   // 用于stringstream
#include <stdexcept> 
#include <iostream> 
using namespace std;

vector<Capability*> CapInterfaceManager::getCapabilityFromTxt(const char* filePath) const{
    vector<Capability*> capabilities;
    ifstream file(filePath);
    if (!file.is_open()) {
        cerr << "无法打开能力文件: " << filePath << endl;
        return capabilities;
    }

    string line;
    while (getline(file, line)) {
        // 跳过注释和空行
        if (line.empty() || line[0] == '#') continue;

        // 分割行数据（使用|作为分隔符）
        vector<string> parts;
        stringstream ss(line);
        string part;
        while (getline(ss, part, '|')) {
            parts.push_back(part);
        }

        // 校验格式（至少需要10个字段）
        if (parts.size() < 10) {
            cerr << "无效的能力数据格式: " << line << endl;
            continue;
        }

        try {
            // 解析基础属性
            int id = stoi(parts[0]);
            string name = parts[1];
            bool status = stoi(parts[2]) == 1;
            short type = stoi(parts[3]);
            string vehicleName = parts[4];
            float power = stof(parts[5]);

            // 解析参数（分辨率、视场角）
            ParameterBuilder paramBuilder;
            Parameter* param = paramBuilder
                .arg("resolution", parts[6])
                ->arg("fov", parts[7])
                ->build();

            // 解析等级（多维度）
            vector<float> level;
            stringstream levelSs(parts[8]);
            string levelPart;
            while (getline(levelSs, levelPart, ',')) {
                level.push_back(stof(levelPart));
            }

            // 解析位置
            Position pos;
            stringstream posSs(parts[9]);
            string posPart;
            vector<float> posCoords;
            while (getline(posSs, posPart, ',')) {
                posCoords.push_back(stof(posPart));
            }
            if (posCoords.size() == 3) {
                pos.setN(posCoords[0]);  // 代替pos.x
                pos.setE(posCoords[1]);  // 代替pos.y
                pos.setD(posCoords[2]);  // 代替pos.z
            }
            cout<<id<<" "<<name<<' '<<status<<' '<<"1"<<' '<<"0.8"<<' '<<"0.4"<<' '<<"0.1"<<endl;
            // 构建Capability对象
            CapabilityBuilder *capBuilder = new CapabilityBuilder();
            Capability* cap = capBuilder
                ->id(id)
                ->name(name)
                ->status(status)
                ->vehicle(vehicleName)
                ->power(power)
                ->level(level)
                ->parameter(*param)
                ->build();
            cap->setPosition(pos);

            capabilities.push_back(cap);
        } catch (const exception& e) {
            cerr << "解析能力数据失败: " << e.what() << " 行: " << line << endl;
            continue;
        }
    }
    
    file.close();
    return capabilities;
}
