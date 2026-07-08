//
// Created by zhengyanzhu on 2022/11/7.
//

#include "Parameter.h"

ParameterBuilder::ParameterBuilder() {

}

ParameterBuilder *ParameterBuilder::arg(string key, string value) {
    this->args[key] = value;
    return this;
}

const map<string, string> &ParameterBuilder::getArgs() const {
    return args;
}

Parameter *ParameterBuilder::build(){
    res = new Parameter(*this);
    return res;
}

ParameterBuilder::~ParameterBuilder() {
    delete res;
}

Parameter::Parameter(const ParameterBuilder &temp) {
    this->args = temp.getArgs();
}

Parameter::Parameter() {

}

Parameter::Parameter(map<string, string> args) {
    this->args = args;
}

Parameter::~Parameter() {

}

const map<string, string> &Parameter::getArgs() const{
    return args;
}

string Parameter::get(string key) {
    if(args.count(key) == 0){
        return "null";
    }
    return args[key];
}

bool Parameter::set(string key, string val) {
    if(args.count(key) == 0){
        return false;
    }
    args[key] = val;
    return true;
}
