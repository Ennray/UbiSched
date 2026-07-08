import numpy as np
from pandas.conftest import axis_1
from sympy import false
from sympy.core.random import random
from torch.nn import Sigmoid
from tornado.process import task_id
import random

class EnvCore(object):
    """
    # 环境中的智能体
    """

    def __init__(self):
        self.agent_num = 2  # 设置智能体(小飞机)的个数，这里设置为两个 # set the number of agents(aircrafts), here set to two               orin 5,6,11
        self.obs_dim = 15   # 设置智能体的观测维度 # set the observation dimension of agents  5个任务，
        self.action_dim = [5,4]  # 设置智能体的动作维度，这里假定为一个五个维度的 # set the action dimension of agents, here set to a five-dimensional
        # self.action_dim =10
        # self.time = 0
        self.last_obs = []
        self.done = false
        self.last_energy = []
        self.available_actions = []
    def reset(self):
        """
        # self.agent_num设定为2个智能体时，返回值为一个list，每个list里面为一个shape = (self.obs_dim, )的观测数据
        # When self.agent_num is set to 2 agents, the return value is a list, each list contains a shape = (self.obs_dim, ) observation data
        """
        self.last_obs = []
        sub_agent_obs = []
        self.last_energy = []
        self.done = False
        self.time = 0

        #初始化动作掩码
        self.available_actions = []
        for _ in (0,range(0,self.agent_num)):
            self.available_actions.append([
                np.ones(self.action_dim[0]),  # 第1个动作维度：5个动作都可用 [1,1,1,1,1]
                np.array([1,1,1,0])  # 第2个动作维度：4个动作都可用 [1,1,1]
                ])
        # 初始化无人机感知资源总能量
        for i in range(0,self.agent_num):
            self.last_energy.append(20)
    #随机初始化任务
        for i in range (0, self.obs_dim):
            if i%3 != 0:
                a = np.random.beta(1.5, 4)*10
                self.last_obs.append(a)
            else:
                a = random.randint(1,2)
                self.last_obs.append(a)

        # self.last_obs = np.zeros(6)
        # x = np.random.beta(1, 19, 1)
        # f1_score_pred = (0.874 - 6.056 * x + 135.812 * np.square(x)) * np.exp(-15.267 * x)
        for i in range(self.agent_num):
            tmp = self.last_obs.copy()
            # tmp.append(self.last_energy[i])
            sub_agent_obs.append(tmp)
        return sub_agent_obs,self.available_actions

    def step(self, actions):
        """
        # self.agent_num设定为2个智能体时，actions的输入为一个2纬的list，每个list里面为一个shape = (self.action_dim, )的动作数据
        # 默认参数情况下，输入为一个list，里面含有两个元素，因为动作维度为5，所里每个元素shape = (5, )
        # When self.agent_num is set to 2 agents, the input of actions is a 2-dimensional list, each list contains a shape = (self.action_dim, ) action data
        # The default parameter situation is to input a list with two elements, because the action dimension is 5, so each element shape = (5, )
        """
        sub_agent_obs = []
        sub_agent_reward = []
        sub_agent_done = []
        sub_agent_info = []
        tmpreward = 0
        # for i in range(self.agent_num):
        #     Single_action = np.where(actions[i] == 1)
        #     task = Single_action[0][0] + 1
        #     if self.last_obs[task] == 0:
        #         tmpreward -= 100
        tmpreward -= self.time * 0.1
        for i in range(self.agent_num):
            Single_action = np.where(actions[i] == 1)
            task = Single_action[0][0] *3
            sensor = Single_action[0][1] - self.action_dim[0]
            weather1 = self.last_obs[task+1]
            weather2 = self.last_obs[task+2]
            F1 = 0.6892 * np.exp(-14.2991*weather1) + 0.1629
            F2 = 2.1795 * np.exp(-2.2711*weather2) - 1.1109
            F = F1*F2
            F = np.clip(F,0,1)
            if self.last_obs[task] == 1:
                if sensor == 0:
                    tmpreward += F - 0.8
                    tmpreward -= 0.05
                    if F>0.2:
                        self.last_obs[task] = 0
                if sensor == 1:
                    tmpreward += 0
                    tmpreward -= 0.15
                    self.last_obs[task] = 0
                if sensor == 2:
                    tmpreward -= 0.3
                    tmpreward -= 0.35
            if self.last_obs[task] == 2:
                if sensor == 0:
                    tmpreward -= 0.3
                    tmpreward -= 0.05
                if sensor == 1:
                    tmpreward -= 0.3
                    tmpreward -= 0.15
                if sensor == 2:
                    tmpreward -= 0.3
                    self.last_obs[task] = 0

            # if self.last_obs[task] == 0:
            #     tmpreward -= 0.3
            # if self.last_obs[task] == 1:  # 目标检测任务
            #     if sensor == 0:
            #         self.last_energy[i] -= 1
            #         if weather == 0:
            #             tmpreward += - 0.05
            #             self.last_obs[task] = 0
            #
            #         if weather == 1:
            #             tmpreward += - 0.15
            #             self.last_obs[task] = 0
            #         if weather == 2:
            #             tmpreward += - 0.55
            #         if weather == 3:
            #             tmpreward -= 0.55
            #     if sensor == 1:
            #         self.last_energy[i] -= 2
            #         if weather == 0:
            #             tmpreward -= 0.6
            #         if weather == 1:
            #             tmpreward -= 0.45
            #         tmpreward += - 0.1
            #         if weather < 1:
            #             tmpreward -= 1
            #         self.last_obs[task] = 0
            #     if sensor == 2:
            #         self.last_energy[i] -= 5
            #         tmpreward -= 0.55
            # if self.last_obs[task] == 2:  # 3D建图任务
            #     if sensor == 0:
            #         tmpreward -= 0.35
            #         self.last_energy[i] -= 1
            #     if sensor == 1:
            #         tmpreward -= 0.4
            #         self.last_energy[i] -= 2
            #     if sensor == 2:
            #         tmpreward += -0.25
            #         self.last_energy[i] -= 5
            #         self.last_obs[task] = 0

            sub_agent_info.append({})
        for i in range(0,5):
            w1 = 3*i+1
            w2 = 3*i+2
            new_weather = random.randint(0, 1)
            self.last_obs[w1] = new_weather
            new_weather = random.randint(0, 1)
            self.last_obs[w2] = new_weather

        for i in range(self.agent_num):
            tmp = self.last_obs.copy()
            # tmp.append(self.last_energy[i])
            sub_agent_obs.append(tmp)
            if self.done == True:
                sub_agent_done.append(True)
            else:
                sub_agent_done.append(False)
        if all(self.last_obs[i] == 0 for i in range(0, len(self.last_obs), 3)):
            self.done = True
            tmpreward += 1
        # if all(i == 0 for i in self.last_energy):
        #     self.done = True

        for i in range(self.agent_num):
            sub_agent_reward.append(np.array([tmpreward]))
        for i in range(0, len(self.last_obs), 3):                             #处理动作掩码
            if self.last_obs[i] == 0:
                for j in range(0,self.agent_num):
                    self.available_actions[j][0][i//3] = 0
        # for i in range(0,self.agent_num):                                   #处理传感器掩码
        #     if self.last_energy[i] < 5:
        #         self.available_actions[i][1][2] = 0
        #     if self.last_energy[i] < 2:
        #         self.available_actions[i][1][1] = 0
        #     if self.last_energy[i] < 1:
        #         self.available_actions[i][1][0] = 0
        #         self.available_actions[i][1][3] = 1


        return [sub_agent_obs, sub_agent_reward, sub_agent_done, sub_agent_info],self.available_actions

