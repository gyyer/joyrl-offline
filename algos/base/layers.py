#!/usr/bin/env python
# coding=utf-8
'''
Author: JiangJi
Email: johnjim0816@gmail.com
Date: 2023-04-16 12:08:14
LastEditor: JiangJi
LastEditTime: 2023-04-16 12:08:30
Discription: 
'''


import torch.nn as nn
import torch.nn.functional as F
activation_dics = {'relu': nn.ReLU, 'tanh': nn.Tanh, 'sigmoid': nn.Sigmoid, 'softmax': nn.Softmax,'none': nn.Identity}             
def linear_layer(in_dim,out_dim,act_name='relu'):
    """ 生成一个线性层
        layer_dim: 线性层的输入输出维度
        activation: 激活函数
    """
    return nn.Sequential(nn.Linear(in_dim,out_dim),activation_dics[act_name]())