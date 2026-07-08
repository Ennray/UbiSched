//
// Created by zhengyanzhu on 2022/11/27.
//

#ifndef DEMOPLUGIN_POSITION_H
#define DEMOPLUGIN_POSITION_H
#include <string>

using namespace std;

class Position {
private:
    float n;
    float e;
    float d;
    string time;
public:
    const string &getTime() const;

public:
    Position(float n, float e, float d, const string &time);

    virtual ~Position();

    Position();

    float getN() const;

    float getE() const;

    float getD() const;

    void setN(float n);

    void setE(float e);

    void setD(float d);

    void setTime(const string &time);
};
#endif //DEMOPLUGIN_POSITION_H
