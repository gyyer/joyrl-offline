#!/usr/bin/env python
# coding=utf-8


import torch
import torch.nn as nn
import torch.optim as optim
from torch.nn.utils import clip_grad_norm_
import torch.nn.functional as F
import random
import math
import numpy as np
from common.layers import QNetwork
from common.memories import ReplayBuffer
from common.optms import SharedAdam

class Agent:
    def __init__(self,cfg, is_share_agent = False):

        self.n_actions = cfg.n_actions  
        self.device = torch.device(cfg.device) 
        self.gamma = cfg.gamma  
        self.tau = cfg.tau
        ## e-greedy parameters
        self.sample_count = 0  # sample count for epsilon decay
        self.epsilon_start = cfg.epsilon_start
        self.epsilon_end = cfg.epsilon_end
        self.epsilon_decay = cfg.epsilon_decay
        self.batch_size = cfg.batch_size
        self.target_update = cfg.target_update
        self.policy_net = QNetwork(cfg).to(self.device)
        # summary(self.policy_net, (1,4))
        self.target_net = QNetwork(cfg).to(self.device)
        ## copy parameters from policy net to target net
        # for target_param, param in zip(self.target_net.parameters(),self.policy_net.parameters()): 
        #     target_param.data.copy_(param.data)
        self.target_net.load_state_dict(self.policy_net.state_dict()) # or use this to copy parameters
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=cfg.lr) 
        if is_share_agent:
            self.policy_net.share_memory()
            self.target_net.share_memory()
            self.optimizer = SharedAdam(self.policy_net.parameters(), lr=cfg.lr)
            self.optimizer.share_memory()
        self.memory = ReplayBuffer(cfg.buffer_size)
        self.update_flag = False 
        
    def sample_action(self, state):
        ''' sample action with e-greedy policy
        '''
        self.sample_count += 1
        # epsilon must decay(linear,exponential and etc.) for balancing exploration and exploitation
        self.epsilon = self.epsilon_end + (self.epsilon_start - self.epsilon_end) * \
            math.exp(-1. * self.sample_count / self.epsilon_decay) 
        if random.random() > self.epsilon:
            with torch.no_grad():
                state = torch.tensor(np.array(state), device=self.device, dtype=torch.float32).unsqueeze(dim=0)
                q_values = self.policy_net(state)
                action = q_values.max(1)[1].item() # choose action corresponding to the maximum q value
        else:
            action = random.randrange(self.n_actions)
        return action
    
    def predict_action(self,state):
        ''' predict action
        '''
        with torch.no_grad():
            state = torch.tensor(np.array(state), device=self.device, dtype=torch.float32).unsqueeze(dim=0)
            q_values = self.policy_net(state)
            action = q_values.max(1)[1].item() # choose action corresponding to the maximum q value
        return action
    
    def update(self, share_agent=None):
        if len(self.memory) < self.batch_size: # when transitions in memory donot meet a batch, not update
            return
        else:
            if not self.update_flag:
                # print("Begin to update!")
                self.update_flag = True
        # sample a batch of transitions from replay buffer
        state_batch, action_batch, reward_batch, next_state_batch, done_batch = self.memory.sample(
            self.batch_size)
        state_batch = torch.tensor(np.array(state_batch), device=self.device, dtype=torch.float) # shape(batchsize,n_states)
        action_batch = torch.tensor(action_batch, device=self.device).unsqueeze(1) # shape(batchsize,1)
        reward_batch = torch.tensor(reward_batch, device=self.device, dtype=torch.float).unsqueeze(1) # shape(batchsize,1)
        next_state_batch = torch.tensor(np.array(next_state_batch), device=self.device, dtype=torch.float) # shape(batchsize,n_states)
        done_batch = torch.tensor(np.float32(done_batch), device=self.device).unsqueeze(1) # shape(batchsize,1)
        # print(state_batch.shape,action_batch.shape,reward_batch.shape,next_state_batch.shape,done_batch.shape)
        with torch.no_grad():
            # compute max(Q(s_t+1,A_t+1)) respects to actions A, next_max_q_value comes from another net and is just regarded as constant for q update formula below, thus should detach to requires_grad=False
            next_max_q_value_batch = self.target_net(next_state_batch).max(1)[0].detach().unsqueeze(1)
            # compute expected q value, for terminal state, done_batch[0]=1, and expected_q_value=rewardcorrespondingly
            expected_q_value_batch = reward_batch + self.gamma * next_max_q_value_batch* (1-done_batch)
        # compute current Q(s_t)
        q_value_batch = self.policy_net(state_batch)
        # compute current Q(s_t,a), it is 'y_j' in pseucodes
        real_q_value_batch = q_value_batch.gather(dim=1, index=action_batch) # shape(batchsize,1),requires_grad=True
        # compute regularization and KL divergence term
        cql1_loss = torch.logsumexp(q_value_batch, dim=1).mean() - q_value_batch.mean()
        # compute Bellman error
        bellmann_error = F.mse_loss(real_q_value_batch, expected_q_value_batch)
        # final loss
        q1_loss = cql1_loss + 0.5 * bellmann_error
        # backpropagation
        q1_loss.backward()
        clip_grad_norm_(self.policy_net.parameters(), 1)
        self.optimizer.step()


        # ------------------- update target network ------------------- #
        for target_param, local_param in zip(self.target_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(self.tau*local_param.data + (1.0-self.tau)*target_param.data)



    def save_model(self, fpath):
        from pathlib import Path
        # create path
        Path(fpath).mkdir(parents=True, exist_ok=True)
        torch.save(self.target_net.state_dict(), f"{fpath}/checkpoint.pt")

    def load_model(self, fpath):
        self.target_net.load_state_dict(torch.load(f"{fpath}/checkpoint.pt"))
        for target_param, param in zip(self.target_net.parameters(), self.policy_net.parameters()):
            param.data.copy_(target_param.data)
