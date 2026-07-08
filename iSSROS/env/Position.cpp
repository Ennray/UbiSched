//
// Created by zhengyanzhu on 2022/11/9.
//

#include "Position.h"



Position::Position() {}

Position::~Position() {

}

float Position::getN() const {
    return n;
}

void Position::setN(float n) {
    Position::n = n;
}

void Position::setE(float e) {
    Position::e = e;
}

void Position::setD(float d) {
    Position::d = d;
}

float Position::getE() const {
    return e;
}

float Position::getD() const {
    return d;
}

const string &Position::getTime() const {
    return time;
}

void Position::setTime(const string &time) {
    Position::time = time;
}

Position::Position(float n, float e, float d, const string &time) : n(n), e(e), d(d), time(time) {}
