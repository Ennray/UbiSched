//
// Created by zhengyanzhu on 2022/11/11.
//

#ifndef IROS_PARAMETER_H
#define IROS_PARAMETER_H

#include <map>
using namespace std;

class Parameter;

class ParameterBuilder {
public:
    ParameterBuilder();
    ParameterBuilder* arg(string key, string value);
    Parameter* build();
    const map<string, string> &getArgs() const;
    ~ParameterBuilder();

private:
    map<string,string> args;
    Parameter* res;
};

class Parameter{
public:
    Parameter();
    Parameter(map<string,string> args);
    Parameter(ParameterBuilder const & temp);
    const map<string,string>& getArgs()const;
    string get(string key);
    bool set(string key,string val);
    virtual ~Parameter();

private:
    map<string,string> args;
};


#endif //IROS_PARAMETER_H
