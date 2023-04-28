#!/usr/bin/env python
# coding=utf-8
'''
Author: JiangJi
Email: johnjim0816@gmail.com
Date: 2023-04-17 13:27:23
LastEditor: JiangJi
LastEditTime: 2023-04-28 16:43:13
Discription: 
'''
import ray
import asyncio


@ray.remote(num_cpus=1)
class Interactor:
    def __init__(self, cfg, id = None, env = None, policy = None, ):
        self.cfg = cfg
        self.id = id # interactor id
        self.env = env
        self.policy = policy
    async def run(self, data_server):
        while not await data_server.check_episode_limit.remote():
            ep_reward = 0
            ep_step = 0
            self.load_policy(data_server)
            state = self.env.reset()
            for _ in range(self.cfg.max_step):
                action = self.policy.sample_action(state)
                next_state, reward, terminated, truncated , info = self.env.step(action)
                ep_reward += reward
                ep_step += 1
                await data_server.enqueue_exp.remote((state, action, reward, next_state, terminated, info))
                if terminated:
                    break
    def load_policy(self, data_server):
        policy_params = ray.get(data_server.dequeue_policy_params.remote())
        self.policy.load_params(policy_params)