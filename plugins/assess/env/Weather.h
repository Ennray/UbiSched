//
// Created by zhengyanzhu on 2022/11/11.
//

#ifndef IROS_WEATHER_H
#define IROS_WEATHER_H

#include <iostream>

using namespace std;

class Weather;
class WeatherBuilder{
public:
    WeatherBuilder();
    WeatherBuilder* fog(float val);
    WeatherBuilder* rain(float val);
    WeatherBuilder* dust(float val);
    WeatherBuilder* time(string val);
    Weather * build();
    ~WeatherBuilder();

public:
    string defaultTime;
    float defaultFog;
    float defaultRain;
    float defaultDust;
    Weather* res;
};

class Weather {
public:
    Weather();
    Weather(Weather& temp);
    Weather(WeatherBuilder& temp);
    virtual ~Weather();
    float getFog() const;
    void setFog(float val);
    const string getTime() const;
    void setTime(const string time);
    void show();
    float getRain() const;
    void setRain(float rain);
    float getDust() const;
    void setDust(float dust);

private:
    string time;
    float fog;
    float rain;
    float dust;
};

#endif //IROS_WEATHER_H
