//
// Created by zhengyanzhu on 2022/11/20.
//

#include "Resource.h"

Resource::Resource() {}

Resource::~Resource() {

}

const string &Resource::getResourceName() const {
    return resourceName;
}

int Resource::getTaskid() const {
    return taskid;
}

void Resource::setResourceName(const string &name) {
    Resource::resourceName = name;
}

void Resource::setImageType(int imageType) {
    Resource::imageType = imageType;
}

int Resource::getImageType() const {
    return imageType;
}

const string &Resource::getVehicleName() const {
    return vehicleName;
}

void Resource::setVehicleName(const string &vehicleName) {
    Resource::vehicleName = vehicleName;
}
void Resource::setTaskid(int taskid){
    Resource::taskid = taskid;
}