#!/usr/bin/env python
# coding=utf-8
'''
Author: JiangJi
Email: johnjim0816@gmail.com
Date: 2023-04-16 12:06:20
LastEditor: JiangJi
LastEditTime: 2023-04-16 12:08:00
Discription: 
'''
class BaseExp:
    def __init__(self,state=None, action=None, reward=None, next_state=None, terminated=None, **kwargs):
        self.state = state
        self.action = action
        self.reward = reward
        self.next_state = next_state
        self.terminated = terminated