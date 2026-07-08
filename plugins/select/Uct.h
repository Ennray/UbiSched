#pragma once
#include <vector>
#include <cmath>
#include <iostream>


class Uct {
public:
    Uct(double c = 1.0) : c_(c), total_count_(0) {}
    void AddResult(double result) {
        total_count_++;
        results_.push_back(result);
    }
    double GetUpperConfidenceBound() {
        double mean = 0.0;
        for (auto result : results_) {
            mean += result;
        }
        mean /= results_.size();

        double std_error = 0.0;
        if (results_.size() > 1) {
            double sum_squares = 0.0;
            for (auto result : results_) {
                sum_squares += pow(result - mean, 2);
            }
            std_error = sqrt(sum_squares / (results_.size() - 1));
        }

        return mean + c_ * std_error;
    }
    int GetTotalCount() {
        return total_count_;
    }

private:
    double c_;
    int total_count_;
    std::vector<double> results_;
};

//这个类包含了以下几个函数：
//
//构造函数UpperConfidenceBound(double c = 1.0)：初始化置信区间常数c和总的样本数为0。
//AddResult(double result)：向样本中添加一个结果。
//GetUpperConfidenceBound()：计算并返回当前样本的上置信区间。
//GetTotalCount()：获取当前样本的总数。
//在使用这个类时，需要先创建一个对象，然后通过AddResult方法将蒙特卡洛树搜索的每次模拟结果添加到样本中，最后调用GetUpperConfidenceBound方法计算上置信区间。例如：
//
//cpp
//
//        UpperConfidenceBound ucb(1.0);
//
//for (int i = 0; i < 1000; i++) {
//double result = simulate(); // 模拟蒙特卡洛树搜索并返回结果
//ucb.AddResult(result);
//}
//
//double upper_confidence_bound = ucb.GetUpperConfidenceBound();
//int total_count = ucb.GetTotalCount();
//其中simulate函数需要根据具体问题进行编写，它的返回值为蒙特卡洛树搜索的结果，可以是胜率、分数、奖励等等。在本例中，上置信区间的常数c取1.0，可以根据具体需求进行调整。