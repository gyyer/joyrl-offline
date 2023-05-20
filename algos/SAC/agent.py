
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from torch.distributions import Normal
from common.memories import ReplayBuffer
import random
import math
import numpy as np

LOG_SIG_MAX = 2 # 一个常数，用于限制高斯策略网络输出的对数标准差的最大值
LOG_SIG_MIN = -20 # 一个常数，用于限制高斯策略网络输出的对数标准差的最小值
epsilon = 1e-6 # 一个非常小的数


def weights_init_(m):
    '''对神经网络的权重进行初始化
    Args:
        m (整数): 是一个 nn.Module 对象
    '''
    if isinstance(m, nn.Linear):
        torch.nn.init.xavier_uniform_(m.weight, gain=1)
        torch.nn.init.constant_(m.bias, 0)

class QNetwork(nn.Module):
    '''神经网络模型：用于估计给定状态的价值函数
    Args:
        nn : 继承 nn.Module
    '''
    def __init__(self, num_inputs, hidden_dim):
        super(QNetwork, self).__init__()

        self.linear1 = nn.Linear(num_inputs, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, hidden_dim)
        self.linear3 = nn.Linear(hidden_dim, 1)

        self.apply(weights_init_)

    def forward(self, state):
        x = F.relu(self.linear1(state))
        x = F.relu(self.linear2(x))
        x = self.linear3(x)
        return x

class QNetwork(nn.Module):
    '''估计状态-动作对的 Q 值
    Args:
        nn : 继承 nn.Module
    '''
    def __init__(self, num_inputs, num_actions, hidden_dim):
        super(QNetwork, self).__init__()

        # Q1 结构
        self.linear1 = nn.Linear(num_inputs + num_actions, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, hidden_dim)
        self.linear3 = nn.Linear(hidden_dim, 1)

        # Q2 结构
        self.linear4 = nn.Linear(num_inputs + num_actions, hidden_dim)
        self.linear5 = nn.Linear(hidden_dim, hidden_dim)
        self.linear6 = nn.Linear(hidden_dim, 1)

        self.apply(weights_init_)

    def forward(self, state, action):
        xu = torch.cat([state, action], 1)
        
        x1 = F.relu(self.linear1(xu))
        x1 = F.relu(self.linear2(x1))
        x1 = self.linear3(x1)

        x2 = F.relu(self.linear4(xu))
        x2 = F.relu(self.linear5(x2))
        x2 = self.linear6(x2)

        return x1, x2


class GaussianPolicy(nn.Module):
    '''高斯策略网络：用于输出动作的均值和方差
    Args:
        nn : 继承 nn.Module
    '''
    def __init__(self, num_inputs, num_actions, hidden_dim, action_space=None):
        super(GaussianPolicy, self).__init__()
        
        self.linear1 = nn.Linear(num_inputs, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, hidden_dim)

        self.mean_linear = nn.Linear(hidden_dim, num_actions)
        self.log_std_linear = nn.Linear(hidden_dim, num_actions)

        self.apply(weights_init_)

        ## 将策略网络输出的动作进行缩放和平移
        if action_space is None:
            self.action_scale = torch.tensor(1.)
            self.action_bias = torch.tensor(0.)
        else:
            self.action_scale = torch.FloatTensor(
                (action_space.high - action_space.low) / 2.)
            self.action_bias = torch.FloatTensor(
                (action_space.high + action_space.low) / 2.)

    def forward(self, state):
        x = F.relu(self.linear1(state))
        x = F.relu(self.linear2(x))
        mean = self.mean_linear(x)
        log_std = self.log_std_linear(x)
        log_std = torch.clamp(log_std, min=LOG_SIG_MIN, max=LOG_SIG_MAX)
        return mean, log_std

    def sample(self, state):
        mean, log_std = self.forward(state)
        std = log_std.exp()
        normal = Normal(mean, std)
        x_t = normal.rsample()  # 重新参数化的技巧 (mean + std * N(0,1))
        y_t = torch.tanh(x_t)

        action = y_t * self.action_scale + self.action_bias
        log_prob = normal.log_prob(x_t)
        # Enforcing Action Bound
        # log_prob -= (2 * (math.log(2) - x_t - F.softplus(-2 * x_t))).sum(1, keepdim=True)

        log_prob -= torch.log(self.action_scale * (1 - y_t.pow(2)) + epsilon)
        log_prob = log_prob.sum(1, keepdim=True)
        mean = torch.tanh(mean) * self.action_scale + self.action_bias
        # print ("action = ", action)
        return action, log_prob, mean

    def to(self, device):
        self.action_scale = self.action_scale.to(device)
        self.action_bias = self.action_bias.to(device)
        return super(GaussianPolicy, self).to(device)


class DeterministicPolicy(nn.Module):
    '''确定性策略类：用于确定性策略优化算法中的行动选择
    Args:
        nn : nn.Module
    '''
    def __init__(self, num_inputs, num_actions, hidden_dim, action_space=None):
        super(DeterministicPolicy, self).__init__()
        self.linear1 = nn.Linear(num_inputs, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, hidden_dim)

        self.mean = nn.Linear(hidden_dim, num_actions)
        self.noise = torch.Tensor(num_actions)

        self.apply(weights_init_)

        ## 将策略网络输出的动作进行缩放和平移
        if action_space is None:
            self.action_scale = 1.
            self.action_bias = 0.
        else:
            self.action_scale = torch.FloatTensor(
                (action_space.high - action_space.low) / 2.)
            self.action_bias = torch.FloatTensor(
                (action_space.high + action_space.low) / 2.)

    def forward(self, state):
        x = F.relu(self.linear1(state))
        x = F.relu(self.linear2(x))
        mean = torch.tanh(self.mean(x)) * self.action_scale + self.action_bias
        return mean

    def sample(self, state):
        mean = self.forward(state)
        noise = self.noise.normal_(0., std=0.1)
        noise = noise.clamp(-0.25, 0.25)
        action = mean + noise
        return action, torch.tensor(0.), mean

    def to(self, device):
        self.action_scale = self.action_scale.to(device)
        self.action_bias = self.action_bias.to(device)
        self.noise = self.noise.to(device)
        return super(DeterministicPolicy, self).to(device)

class Agent:
    def __init__(self,cfg) -> None:
        '''智能体类
        Args:
            cfg (class): 超参数类
        '''
        self.n_states = cfg.n_states
        self.n_actions = cfg.n_actions
        self.action_space = cfg.action_space
        self.continous = cfg.continous
        self.sample_count = 0
        self.update_count = 0
        self.gamma = cfg.gamma
        self.tau = cfg.tau
        self.alpha = cfg.alpha
        self.start_steps = cfg.start_steps
        self.n_epochs = cfg.n_epochs
        self.policy_type = cfg.policy_type
        self.target_update_fre = cfg.target_update_fre
        self.automatic_entropy_tuning = cfg.automatic_entropy_tuning
        self.batch_size = cfg.batch_size
        self.memory = ReplayBuffer(cfg.buffer_size)
        self.device = torch.device(cfg.device) 
        self.critic = QNetwork(cfg.n_states,cfg.n_actions, cfg.hidden_dim).to(device=self.device)
        self.critic_optim = Adam(self.critic.parameters(), lr=cfg.lr)
        self.critic_target = QNetwork(cfg.n_states, cfg.n_actions, cfg.hidden_dim).to(self.device)
        for target_param, param in zip(self.critic_target.parameters(), self.critic.parameters()):
            target_param.data.copy_(param.data)
            
        if cfg.policy_type == "Gaussian":
            # Target Entropy = −dim(A) (e.g. , -6 for HalfCheetah-v2) as given in the paper
            if self.automatic_entropy_tuning is True:
                self.target_entropy = -torch.prod(torch.Tensor(self.action_space.shape).to(self.device)).item()
                self.log_alpha = torch.zeros(1, requires_grad=True, device=self.device)
                self.alpha_optim = Adam([self.log_alpha], lr=cfg.lr)

            self.policy = GaussianPolicy(cfg.n_states, cfg.n_actions, cfg.hidden_dim, self.action_space).to(self.device)
            self.policy_optim = Adam(self.policy.parameters(), lr=cfg.lr)

        else:
            self.alpha = 0
            self.automatic_entropy_tuning = False
            self.policy = DeterministicPolicy(cfg.n_states, cfg.n_actions, cfg.hidden_dim, self.action_space).to(self.device)
            self.policy_optim = Adam(self.policy.parameters(), lr=cfg.lr)
    def sample_action(self,state):
        self.sample_count+=1
        if self.sample_count < self.start_steps:
            action = self.action_space.sample()
            return action
        else:
            state = torch.tensor(state, device=self.device, dtype=torch.float32).unsqueeze(0)
            action, _, _ = self.policy.sample(state)
            return action.detach().cpu().numpy()[0]
    def predict_action(self,state):
        state = torch.tensor(state, device=self.device, dtype=torch.float32).unsqueeze(0)
        _, _, action = self.policy.sample(state)
        return action.detach().cpu().numpy()[0]
    def update(self):
        '''更新 Q 网络和策略网络参数
        '''
        if len(self.memory) < self.batch_size: # 检查回访缓冲区中是否有足够的 transitions 形成一个批次，如果没有则返回不进行更新
            return
        for i in range(self.n_epochs):
            self.update_count += 1 # 累加循环次数
            state_batch, action_batch, reward_batch, next_state_batch, done_batch = self.memory.sample(batch_size=self.batch_size)
            ## 完成从回放缓冲区中采样一个批次的转换，然后将状态动作，奖励，下一个状态和完成转换标志转换为 PyTorch 张量，并将其移动到设备上来
            state_batch = torch.FloatTensor(state_batch).to(self.device)
            next_state_batch = torch.FloatTensor(next_state_batch).to(self.device)
            action_batch = torch.FloatTensor(action_batch).to(self.device)
            reward_batch = torch.FloatTensor(reward_batch).to(self.device).unsqueeze(1)
            done_batch = torch.FloatTensor(done_batch).to(self.device).unsqueeze(1)
            # print ("done_batch = ", done_batch)
            with torch.no_grad(): 
                next_state_action, next_state_log_pi, _ = self.policy.sample(next_state_batch) # 使用策略网络从下一个状态中采样下一个动作
                qf1_next_target, qf2_next_target = self.critic_target(next_state_batch, next_state_action) # 使用评论家目标网络计算下一个状态的 Q 值
                min_qf_next_target = torch.min(qf1_next_target, qf2_next_target) - self.alpha * next_state_log_pi # 计算下一个状态的最小 Q 值
                next_q_value = reward_batch + (1 - done_batch) * self.gamma * (min_qf_next_target) # 计算目标 Q 值

            qf1, qf2 = self.critic(state_batch, action_batch)  # 使用评论家网络计算当前状态和动作的 Q 值。在政策改进步骤中，两个 q 函数可以缓解正向偏差
            qf1_loss = F.mse_loss(qf1, next_q_value)  # JQ = 𝔼(st,at)~D[0.5(Q1(st,at) - r(st,at) - γ(𝔼st+1~p[V(st+1)]))^2]
            qf2_loss = F.mse_loss(qf2, next_q_value)  # JQ = 𝔼(st,at)~D[0.5(Q1(st,at) - r(st,at) - γ(𝔼st+1~p[V(st+1)]))^2]
            qf_loss = qf1_loss + qf2_loss # 计算评论家网络的总损失

            self.critic_optim.zero_grad() # 清空梯度
            qf_loss.backward() # 计算梯度
            for param in self.critic.parameters():  
                param.grad.data.clamp_(-1, 1) # 限制梯度范围
            self.critic_optim.step() #更新梯度


            pi, log_pi, _ = self.policy.sample(state_batch) # 从策略网络中采样动作
            qf1_pi, qf2_pi = self.critic(state_batch, pi) # 计算当前状态和采样的动作的Q值
            min_qf_pi = torch.min(qf1_pi, qf2_pi) # 计算两个Q值中的最小值，作为当前状态和采样的动作的Q值
            policy_loss = ((self.alpha * log_pi) - min_qf_pi).mean() # Jπ = 𝔼st∼D,εt∼N[α * logπ(f(εt;st)|st) − Q(st,f(εt;st))]
            self.policy_optim.zero_grad() # 清空梯度
            policy_loss.backward() # 计算梯度
            for param in self.policy.parameters():  
                param.grad.data.clamp_(-1, 1) # 限制梯度范围         
            self.policy_optim.step() # 更新梯度


            ##判断是否进行自动熵调整
            if self.automatic_entropy_tuning:
                alpha_loss = -(self.log_alpha * (log_pi + self.target_entropy).detach()).mean()

                self.alpha_optim.zero_grad()
                alpha_loss.backward()
                self.alpha_optim.step()

                self.alpha = self.log_alpha.exp()
                alpha_tlogs = self.alpha.clone() # For TensorboardX logs
            else:
                alpha_loss = torch.tensor(0.).to(self.device)
                alpha_tlogs = torch.tensor(self.alpha) # For TensorboardX logs

            # 软更新，判断是否需要更新目标网络和目标网络中的参数
            if self.update_count % self.target_update_fre == 0:
                for target_param, param in zip(self.critic_target.parameters(), self.critic.parameters()):
                    target_param.data.copy_(target_param.data * (1.0 - self.tau) + param.data * self.tau)

    ## 保存模型
    def save_model(self, fpath):
        from pathlib import Path
        # 创建路径
        Path(fpath).mkdir(parents=True, exist_ok=True)
        
        torch.save({'policy_state_dict': self.policy.state_dict(),
                    'critic_state_dict': self.critic.state_dict(),
                    'critic_target_state_dict': self.critic_target.state_dict(),
                    'critic_optimizer_state_dict': self.critic_optim.state_dict(),
                    'policy_optimizer_state_dict': self.policy_optim.state_dict()}, f"{fpath}/checkpoint.pt")
        
    # 加载模型
    def load_model(self, fpath):
        checkpoint = torch.load(f"{fpath}/checkpoint.pt", map_location=self.device)
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.critic.load_state_dict(checkpoint['critic_state_dict'])
        self.critic_target.load_state_dict(checkpoint['critic_target_state_dict'])
        self.critic_optim.load_state_dict(checkpoint['critic_optimizer_state_dict'])
        self.policy_optim.load_state_dict(checkpoint['policy_optimizer_state_dict'])