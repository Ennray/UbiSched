//
// Created by zhengyanzhu on 2022/11/9.
//

#include "Weather.h"

WeatherBuilder::WeatherBuilder() {
    this->defaultFog = 0.0;
    this->defaultRain = 0.0;
    this->defaultDust = 0.0;
}

WeatherBuilder *WeatherBuilder::fog(float val) {
    this->defaultFog = val;
    return this;
}

Weather *WeatherBuilder::build() {
    res = new Weather(*this);
    return res;
}

WeatherBuilder::~WeatherBuilder() {

}

WeatherBuilder *WeatherBuilder::time(string val) {
    this->defaultTime = val;
    return this;
}

WeatherBuilder *WeatherBuilder::rain(float val) {
    this->defaultRain = val;
    return this;
}

WeatherBuilder *WeatherBuilder::dust(float val) {
    this->defaultDust = val;
    return this;
}

float Weather::getFog() const {
    return fog;
}

void Weather::setFog(float val) {
    Weather::fog = val;
}

Weather::Weather() {}

Weather::~Weather() {

}

Weather::Weather(WeatherBuilder &temp) {
    this->fog = temp.defaultFog;
    this->time = temp.defaultTime;
    this->rain = temp.defaultRain;
    this->dust = temp.defaultDust;
}

Weather::Weather(Weather &temp) {
    this->fog = temp.fog;
    this->time = temp.time;
    this->rain = temp.rain;
}

const string Weather::getTime() const {
    return time;
}

void Weather::setTime(string time) {
    Weather::time = time;
}

void Weather::show() {
    cout<<"   fog: "<<fog<<endl;
    cout<<"   rain: "<<rain<<endl;
    cout<<"   dust: "<<dust<<endl;
}

float Weather::getRain() const {
    return rain;
}

void Weather::setRain(float rain) {
    Weather::rain = rain;
}

float Weather::getDust() const {
    return dust;
}

void Weather::setDust(float dust) {
    Weather::dust = dust;
}
