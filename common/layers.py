import torch.nn as nn
import torch.nn.functional as F
activation_dics = {'relu': nn.ReLU, 'tanh': nn.Tanh, 'sigmoid': nn.Sigmoid, 'softmax': nn.Softmax,'none': nn.Identity}             
def linear_layer(in_dim,out_dim,act_name='relu'):
    """ 生成一个线性层
        layer_dim: 线性层的输入输出维度
        activation: 激活函数
    """
    return nn.Sequential(nn.Linear(in_dim,out_dim),activation_dics[act_name]())

def create_layer(layer_type, in_dim,out_dim, act_name='relu'):
    """ 生成一个层
        layer_type: 层的类型
        layer_dim: 层的输入输出维度
        activation: 激活函数
    """
    if layer_type == "linear":
        return linear_layer(in_dim,out_dim, act_name)
    else:
        raise ValueError("layer_type must be linear")

class QNetwork(nn.Module):
    def __init__(self, cfg) -> None:
        super(QNetwork, self).__init__()
        self.layers_cfg = cfg.value_layers # load layers config
        self.layers = nn.ModuleList()
        for layer_cfg in self.layers_cfg:
            layer_type = layer_cfg['layer_type']
            layer_dim = layer_cfg['layer_dim']
            act_name = layer_cfg['activation']
            in_dim, out_dim = layer_dim
            if in_dim == 'n_states':
                in_dim = cfg.n_states
            if out_dim == 'n_actions':
                out_dim = cfg.n_actions
            self.layers.append(create_layer(layer_type,in_dim, out_dim,act_name))
        # self.layers = self.layers.to(cfg.device)
    def forward(self, x):
        for layer in self.layers:
            x = layer(x)
        return x
    
class ActorSoftmax(nn.Module):
    def __init__(self, cfg) -> None:
        super(ActorSoftmax, self).__init__()
        self.layers_cfg = cfg.actor_layers # load layers config
        self.layers = nn.ModuleList()
        for layer_cfg in self.layers_cfg:
            layer_type = layer_cfg['layer_type']
            layer_dim = layer_cfg['layer_dim']
            act_name = layer_cfg['activation']
            in_dim, out_dim = layer_dim
            if in_dim == 'n_states':
                in_dim = cfg.n_states
            if out_dim == 'n_actions':
                out_dim = cfg.n_actions
            self.layers.append(create_layer(layer_type,in_dim, out_dim,act_name))
        # self.layers = self.layers.to(cfg.device)
    def forward(self, x):
        for layer in self.layers[:-1]:
            x = layer(x)
        x = F.softmax(self.layers[-1](x))
        return x
class Critic(nn.Module):
    def __init__(self, cfg) -> None:
        super(Critic, self).__init__()
        self.layers_cfg = cfg.critic_layers # load layers config
        self.layers = nn.ModuleList()
        for layer_cfg in self.layers_cfg:
            layer_type = layer_cfg['layer_type']
            layer_dim = layer_cfg['layer_dim']
            act_name = layer_cfg['activation']
            in_dim, out_dim = layer_dim
            if in_dim == 'n_states':
                in_dim = cfg.n_states
            self.layers.append(create_layer(layer_type,in_dim, out_dim,act_name))
        # self.layers = self.layers.to(cfg.device)
    def forward(self, x):
        for layer in self.layers:
            x = layer(x)
        return x