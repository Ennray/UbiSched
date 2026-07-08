//
// Created by zhengyanzhu on 2022/11/20.
//

#ifndef IROS_RESOURCE_H
#define IROS_RESOURCE_H
#include <string>

using namespace std;

class Resource {
private:
    string resourceName;
    string vehicleName;
    int imageType;
    int taskid;
public:
    Resource();
    virtual ~Resource();
    const string &getResourceName() const;
    int getImageType() const;
    void setResourceName(const string &name);
    void setVehicleName(const string &vehicleName);
    void setImageType(int imageType);
    const string &getVehicleName() const;
    void setTaskid(int imageType);
    int getTaskid() const;
};


#endif //IROS_RESOURCE_H
