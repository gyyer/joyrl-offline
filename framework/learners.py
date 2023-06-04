import ray
from ray.util.queue import Queue, Empty, Full
class BaseLearner:
    def __init__(self, cfg, id = 0, policy = None, data_handler=None, online_tester=None) -> None:
        self.cfg = cfg
        self.id = id
        self.policy = policy
        self.data_handler = data_handler
        self.online_tester = online_tester
    def add_exps(self,exps):
        ''' add exps to data handler
        '''
        self.data_handler.add_exps(exps)
    def get_policy(self):
        return self.policy
    def get_training_data(self):
        ''' get training data
        '''
        return self.data_handler.sample_training_data()
    def get_model_params(self):
        ''' get model parameters
        '''
        return self.policy.get_model_params()
    def set_model_params(self,model_params):
        ''' set model parameters
        '''
        self.policy.set_model_params(model_params)
    def learn(self, training_data, *args, **kwargs):
        raise NotImplementedError
    
class SimpleLearner(BaseLearner):
    def __init__(self, cfg, id = 0, policy = None, data_handler=None, online_tester=None) -> None:
        super().__init__(cfg, id, policy, data_handler, online_tester)
        self.update_step = 0
    def learn(self, training_data, logger = None, stats_recorder = None, *args, **kwargs):
        if training_data is None: return None # if no training data, return
        self.update_step += 1
        self.policy.learn(**training_data,update_step=self.update_step)
        # self.data_handler.add_data_after_learn(self.policy.data_after_train)
        if self.update_step % self.cfg.model_save_fre == 0:
            self.policy.save_model(f"{self.cfg.model_dir}/{self.update_step}")
            if self.cfg.online_eval == True:
                best_flag, online_eval_reward = self.online_tester.eval(self.policy)
                logger.info(f"learner id: {self.id}, update_step: {self.update_step}, online_eval_reward: {online_eval_reward:.3f}")
                if best_flag:
                    logger.info(f"learner {self.id} for current update step obtain a better online_eval_reward: {online_eval_reward:.3f}, save the best model!")
                    self.policy.save_model(f"{self.cfg.model_dir}/best")
        if self.update_step % self.cfg.model_summary_fre == 0:
            stats_recorder.add_summary((self.update_step, self.policy.summary['scalar']), writter_type = 'model')

    def run(self, training_data, logger = None, stats_recorder = None,  *args, **kwargs):
        if training_data is None: return None
        self.learn(training_data, logger = logger, stats_recorder = stats_recorder)

    
@ray.remote
class RayLearner(BaseLearner):
    ''' learner
    '''
    def __init__(self, cfg, id = 0, policy=None,data_handler=None,online_tester=None) -> None:
        super().__init__(cfg, id, policy, data_handler, online_tester)
        self.model_params_que = Queue(maxsize=128)
    
    def learn(self,training_data, data_server = None, logger = None):
        ''' learn policy
        '''
        if training_data is not None:
            data_server.increase_update_step.remote()
            self.update_step = ray.get(data_server.get_update_step.remote())
            self.policy.learn(**training_data,update_step=self.update_step)
            self.data_handler.add_data_after_learn(self.policy.data_after_train)
            if self.update_step % self.cfg.model_save_fre == 0:
                self.policy.save_model(f"{self.cfg.model_dir}/{self.update_step}")
                if self.cfg.online_eval == True:
                    best_flag, online_eval_reward = ray.get(self.online_tester.eval.remote(self.policy))
                    logger.info.remote(f"learner id: {self.id}, update_step: {self.update_step}, online_eval_reward: {online_eval_reward:.3f}")
                    if best_flag:
                        logger.info.remote(f"learner {self.id} for current update step obtain a better online_eval_reward: {online_eval_reward:.3f}, save the best model!")
                        self.policy.save_model(f"{self.cfg.model_dir}/best")
            return self.update_step, self.policy.summary
        return None, None

