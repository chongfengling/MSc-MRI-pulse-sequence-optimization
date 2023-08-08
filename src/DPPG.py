import numpy as np
import torch
import torch.nn as nn
import time
import matplotlib.pyplot as plt
from utilities import *

# action space: {t1:_, t3:_, d1:_, d2:_, G1:_, G2:_} 6 arrays. 

class Env():
    # Environment, generates state and reward based on action
    def __init__(self):
        pass

    def make(self, env_name, plot=False):
        # create the environment
        if env_name == "Two-Constant-Gradient":
            # x space (spatial space)
            self.FOV_x = 512 # field of view in x space
            self.N = 512 # sampling points in x space (and k space, time space during ADC)
            self.delta_x = self.FOV_x / self.N # sampling interval in x space
            self.x_axis = np.linspace(-self.FOV_x / 2, self.FOV_x / 2 - self.delta_x, self.N) # symmetric x space
            # k space (frequency space)
            self.delta_k = 1 / self.FOV_x # sampling interval in k space
            self.FOV_k = self.delta_k * self.N # field of view in k space
            self.k_axis = np.linspace(-self.FOV_k / 2, self.FOV_k / 2 - self.delta_k, self.N) # symmetric k space
            self.gamma = 2.68e8 # rad/s/T
            self.gamma_bar = 0.5 * self.gamma/np.pi # s^-1T^-1
            # t space (time space) based on G1 and G2
            # create object over x space
            self.density = np.zeros(len(self.x_axis))
            self.density[int(len(self.x_axis) / 4 + len(self.x_axis) / 8): int(len(self.x_axis) / 4 * 3 - len(self.x_axis) / 8)] = 1
            if plot:
                plt.figure(figsize=(10, 6))
                plt.plot(self.x_axis, self.density, '-', label='object')
                plt.legend()
                plt.xlabel('x')
                plt.ylabel('density')
                plt.grid()
                plt.show()
            # prepare for simulation
            # create spins after the rf pulse (lying on the y-axis)
            # assume the spins are lying on each sampling point over y-axis
            self.m0 = 1.0
            self.w_0 = 0
            self.vec_spins = np.zeros((3, self.N))
            self.vec_spins[1, :] = 1

        else:
            raise RuntimeError("Env name not found.")

    def reset(self):
        # reset the environment and return the initial state
        pass

    def action_space_sample(self):
        # return a random action from the action space
        # 6 variables: t1:_, t3:_, d1:_, d2:_, G1symbol:_, G2symbol:_, Gvalues:_
        self.action_low = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0])
        self.action_high = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        self.action_space = np.random.uniform(low=self.action_low, high=self.action_high, size=7)
        

    def step(self, action, plot = False):
        # action is an array of 7 variables (t1, t2, d1, d2, G1symbol, G2symbol, Gvalues)
        # take an action and return the next state, reward, a boolean indicating if the episode is done and additional info
        
        # calculate the gradient values
        (t1, t2, d1, d2, G1symbol, G2symbol, Gvalue) = action
        Gvalue = Gvalue * 1e-6
        gamma_bar_G = self.gamma_bar * Gvalue * 1e-3
        delta_t =  self.delta_k / gamma_bar_G
        Ts = self.FOV_k / gamma_bar_G # ADC duration FIXED
        t_max = 1.5 * Ts - delta_t # maximum time (ms) (rephasing process is 2 times longer than dephasingprocess)
        t_axis = np.linspace(0, t_max, int(self.N * 1.5))
        G_values_array = np.zeros(len(t_axis))
        # two gradient can be overlapped
        G_values_array[int(t1 * len(t_axis)): int(t1 * len(t_axis) + d1 * len(t_axis))] += G1symbol * Gvalue
        G_values_array[int(t2 * len(t_axis)): int(t2 * len(t_axis) + d2 * len(t_axis))] += G2symbol * Gvalue
        k_traj = np.cumsum(G_values_array) * 1e-3
        if plot:
            _, (ax1, ax2) = plt.subplots(2, sharex=True, figsize=(10, 6))
            ax1.plot(t_axis, G_values_array)
            ax1.set_ylabel('Gx (mT/m)')

            ax2.plot(t_axis, k_traj)
            ax2.set_ylabel('k (1/m)')

            ax2.set_xticks([0, t_axis[int(self.N / 2) - 1], t_axis[int(self.N * 1.5) - 1]])
            ax2.set_xticklabels(['$t_1$', r'$t_2 (t_3)$', r'$t_4$'])

            plt.show()
        
        # do relaxation
        # define larmor frequency w_G of spins during relaxation
        # shape = (number of time steps, number of sampling points)
        w_G = np.outer(G_values_array, self.x_axis) * self.gamma * 1e-3 + self.w_0

        res = multiple_Relaxation(self.vec_spins, m0=self.m0, w=0, w0=w_G, t1=1e10, t2=1e10, t=1.5*Ts, steps=int(self.N*1.5), axis='z')

        store = []
        for i in range(2):
            tmp = res[i,:,:].squeeze() # shape: (number of steps, number of sampling points)
            
            store.append(tmp @ self.density) # multiply by true density

        Mx_1, My_1 = store[0][:int(self.N/2)], store[1][:int(self.N/2)]
        Mx_2, My_2 = store[0][int(self.N/2):], store[1][int(self.N/2):]

        # plot the full signal
        signal_Mx = np.concatenate((Mx_1, Mx_2), axis=0)
        signal_My = np.concatenate((My_1, My_2), axis=0)
        adc_signal = Mx_2 * 1 + 1j * My_2
        re_density = np.fft.fftshift(np.fft.ifft(np.fft.fftshift(adc_signal)))
        abs_re_density = np.abs(re_density)
        abs_mse_error = np.abs(np.sum(abs_re_density - self.density))
        plt.plot(self.x_axis, abs_re_density, label='reconstruction')
        plt.plot(self.x_axis, self.density, label='original')
        plt.legend()
        plt.show()
        print(f'error (MSE) {np.sum(np.abs(re_density) - self.density)}')
        info = None

        return abs_re_density, abs_mse_error, False, info

    # def action_space.sample(self):
    #     # return a random action
    #     pass

    def render(self):
        # display the current state of the environment
        pass

    

class ActorNetwork():
    # Actor Network, generates action based on state
    # observation is the state
    def __init__(self, state_space, action_space):
        super(ActorNetwork, self).__init__()

        # Fully-connected layers
        self.fc_layers = nn.Sequential(
            nn.Linear(state_space, 512),
            nn.ReLU(),
            nn.Linear(512, 128),
            nn.ReLU(),
            nn.Linear(128, 32),
            nn.Sigmoid(),
        )

        # Output layer
        self.output_layer = nn.Linear(32, action_space)

    def forward(self, state):
        tmp = self.fc_layers(state)
        out = self.output_layer(tmp)
        return out

class CriticNetwork():
    # Critic Network, generates Q value based on (current?) state and action
    def __init__(self, state_space, action_space):
        super(CriticNetwork, self).__init__()

        # state input stream
        self.state_stream = nn.Sequential(
            nn.Linear(state_space, 128),
            nn.ReLU(),
            nn.Linear(128, 32),
            nn.ReLU()
        )

        # action input stream
        self.action_stream = nn.Sequential(
            nn.Linear(action_space, 16),
            nn.ReLU(),
            nn.Linear(16, 32),
            nn.ReLU()
        )

        # combined layer
        self.combined_layer = nn.Sequential(
            nn.Linear(32 * 2, 128),
            nn.ReLU(),
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.Linear(256, 1)
        )

        def forward(self, state, action):
            state_tmp = self.state_stream(state)
            action_tmp = self.action_stream(action)
            combined = torch.cat((state_tmp, action_tmp), dim=1)
            out = self.combined_layer(combined)
            return out
        

class DPPG():

    def __init__(self, state_space, action_space, env):
        self.state_space = state_space
        self.action_space = action_space

        self.env = env

        self.seed = 215

        # create Actor Network and its target network
        self.actor = ActorNetwork(state_space, action_space)
        self.actor_target = ActorNetwork(state_space, action_space)
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=0.0001) #!
        # make sure the target network has the same weights as the original network
        for target_param, param in zip(self.actor.parameters(), self.actor_target.parameters()):
            target_param.data.copy_(param.data)

        # create Critic Network and its target network
        self.critic = CriticNetwork(state_space, action_space)
        self.critic_target = CriticNetwork(state_space, action_space)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=0.001) #!
        # make sure the target network has the same weights as the original network
        for target_param, param in zip(self.critic.parameters(), self.critic_target.parameters()):
            target_param.data.copy_(param.data)

        # initialize replay buffer
        # self.memory = 
        # self.random_process = 

        # define hyper-parameters
        self.batch_size = 64
        self.tau = 0.001
        self.discount = 0.99
        self.depsilon = 1.0 / 50000

        self.epsilon = 1.0
        self.s_t = None # most recent state
        self.a_t = None # most recent action
        self.is_training = True

    def actor(self, state, exploraion_noise=True):
        # return an action based on the current state with or without exploration noise
        pass

    def store_transition(self, state, action, reward, state_, done):
        pass

    def update_network(self):
        pass

def main():

    def train(agent, env, num_episode = 1000, num_steps_per_ep = 1000):
        for i in range(num_episode): 
            # reset the environment
            state = env.reset()
            # record time and current reward in this episode
            t1 = time.time()
            episode_reward = 0

            for j in range(num_steps_per_ep):
                # return an action based on the current state
                action = agent.actor(state)
                # interact with the environment
                state_, reward, done, info = env.step(action)
                # store the transition
                agent.store_transition(state, action, reward, state_, done)

                # update the network if the replay memory is full
                if agent.memory.is_full():
                    agent.update_network()

                # output records
                state = state_
                episode_reward += reward
                if j == num_steps_per_ep - 1:
                    print(
                        '\rEpisode: {}/{}  | Episode Reward: {:.4f}  | Running Time: {:.4f}'.format(
                            i, num_episode, episode_reward,
                            time.time() - t1
                        ), end=''
                    )

                


