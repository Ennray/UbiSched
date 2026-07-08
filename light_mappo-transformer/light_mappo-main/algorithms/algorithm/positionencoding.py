import numpy as np
import torch
import math



class PositionalEncoding(torch.nn.Module):
    def __init__(self, d_model, max_seq_length):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_seq_length, d_model)  # 初始化位置编码矩阵
        position = torch.arange(0, max_seq_length, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)  # 偶数位置使用正弦函数
        pe[:, 1::2] = torch.cos(position * div_term)  # 奇数位置使用余弦函数
        self.register_buffer('pe', pe.unsqueeze(0))  # 注册为缓冲区

    def forward(self, x):
        # 将位置编码添加到输入中
        return x + self.pe[:, :x.size(1)]

# attention = torch.nn.MultiheadAttention(12,4,batch_first=True)
# data = np.array([[1,2,3,4,5]])
# data = torch.LongTensor(data)
# embedding = torch.nn.Embedding(10,12)
# k0 = embedding(data)
# print(k0)
# PE = PositionalEncoding(12,10)
# k = PE(k0)
# print(k)
# # k = k.squeeze(0)
# print(k.shape)
# attn_output, attn_output_weights = attention(k,k,k)
# pooled = torch.mean(attn_output,dim = 0)
# o = torch.nn.Linear(12,64)
# output = o(pooled)
#
#
#
# print(k)
# print(attn_output)
# print(attn_output_weights.shape)
# print(attn_output_weights)
# print(output.shape)
