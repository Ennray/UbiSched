import sys

import numpy as np
import torch
import time
from torch.onnx.symbolic_opset11 import argsort


from pathlib import Path
project_root = Path(__file__).resolve().parents[1]
model1 = torch.load(str(project_root / "results/MyEnv/5tasks2UAVs/mappo/check/run14/models/actor_agent0.pt"))
# model2 = torch.load(str(project_root / "results/MyEnv/10tasks3UAVs/mappo/check/run6/models/actor_agent1.pt"))
# model3 = torch.load(str(project_root / "results/MyEnv/10tasks3UAVs/mappo/check/run6/models/actor_agent2.pt"))
actions, action_log_probs, rnn_states= model1.forward(obs = np.array([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]),rnn_states = np.zeros((1,1,1,64)),masks = np.ones(1))
# action_log_probs, dist_entropy = model1.evaluate_actions(obs = np.array([1,1,1,1,1,1,1,0,0,1]),rnn_states = np.zeros((1,1,1,64)),masks = np.ones(1),action=torch.tensor([0,1,2,3,4,5,6,7,8,9]))
print(action_log_probs)
# action_log_probs, dist_entropy = model1.evaluate_actions(obs = np.array([1,1,1,1,1,1,1,1,1,1]),rnn_states = np.zeros((1,1,1,64)),masks = np.ones(1),action=torch.tensor([0,1,2,3,4,5,6,7,8,9]))
# print(action_log_probs)




#
# x = torch.zeros(1)
# actions, action_log_probs, rnn_states = model(obs = np.zeros(1),rnn_states = np.zeros((1,1,1,64)),masks = np.ones(1))
# print(actions)
# print(action_log_probs)
# k = 0
# for i in range (0,10000):
#   actions, action_log_probs, rnn_states = model(np.zeros((1,1),float),np.zeros((1,1,64),float),np.ones((1,1),float))
#   if actions[0]>0.5:
#       k+=1
# print(k)
#
# k=0
# for i in range (0,10000):
#   actions, action_log_probs, rnn_states = model(np.ones((1,1),float),np.zeros((1,1,64),float),np.ones((1,1),float))
#   if actions[0]<0.5:
#       k+=1
# print(k)

# model = torch.load(str(project_root / "results/MyEnv/MyEnv/mappo/check/run1/models/critic_agent0.pt"))
# values, rnn_states = model(cent_obs = np.zeros(1),rnn_states = np.zeros((1,1,1,64)),masks = np.ones(1))
# print(values)