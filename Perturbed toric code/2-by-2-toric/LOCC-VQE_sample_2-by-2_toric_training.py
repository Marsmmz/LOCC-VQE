# import os
# os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import tensorcircuit as tc
import tensorflow as tf
import numpy as np
import time
import pdb
import matplotlib.pyplot as plt
import copy

K = tc.set_backend("tensorflow")
ctype, rtype = tc.set_dtype("complex128")
EPSILON = 1e-10

# # dynamical GPU memory allocation
# config = tf.compat.v1.ConfigProto()
# config.gpu_options.allow_growth = True
# sess = tf.compat.v1.Session(config = config)
# tf.compat.v1.keras.backend.set_session(sess) # The name tf.keras.backend.set_session is deprecated. Please use tf.compat.v1.keras.backend.set_session instead.


Geo_Z_interaction = [[[6,8],[1,8],[0,8],[2,8]],
                   [[7,9],[0,9],[1,9],[3,9]],
                   [[2,10],[5,10],[4,10],[6,10]],
                   [[3,11],[4,11],[5,11],[7,11]]]

Geo_X_interaction = [[0,12],[2,12],[3,12],[4,12],
                     [1,13],[3,13],[2,13],[5,13],
                     [4,14],[6,14],[7,14],[0,14],
                     [5,15],[7,15],[6,15],[1,15]]

def toric_syndrome_circuit(theta_Z):
    # theta_Z [16][3]
    # theta_Z = theta_Z*0.0
    toric_syndrome = tc.Circuit(12)
    
        
    for i in range(2*4):
        toric_syndrome.h(i) # initialize all physical qubits to plus state
    for i in range(len(Geo_Z_interaction)):
        for j in range(4):
            toric_syndrome.ry(Geo_Z_interaction[i][j][0],theta=np.pi/2)
            toric_syndrome.rxx(Geo_Z_interaction[i][j][0],Geo_Z_interaction[i][j][1],theta=theta_Z[0][0])
            toric_syndrome.rx(Geo_Z_interaction[i][j][0],theta=theta_Z[0][1])
            toric_syndrome.rx(Geo_Z_interaction[i][j][1],theta=theta_Z[0][2])
            toric_syndrome.ry(Geo_Z_interaction[i][j][0],theta=-np.pi/2)
        
    return toric_syndrome



def correction_circuit(theta_2):
    corr_circuit = tc.Circuit(12)
    for i in range(8):
        corr_circuit.rx(i, theta = theta_2[i][0])
        corr_circuit.ry(i, theta = theta_2[i][1])
        corr_circuit.rz(i, theta = theta_2[i][2])
    
    return corr_circuit



def U1(n, theta_1): # theta_1 shape [(n-1)*18] 
    theta_1 = tf.reshape(theta_1,[16,3]) #use tf functions!
    U1_circuit = toric_syndrome_circuit(theta_1)
    return U1_circuit

def U2(n, theta_2): # theta_2 = g shape[8*3]
    theta_2 = tf.reshape(theta_2,[8,3])
    U2_circuit = correction_circuit(theta_2)
    return U2_circuit

def g_func_batch_wo_grad(gamma, projector_v, CNOT_Ops, masks, n):
    projector_v_encoding_matrix = tf.constant(
        [[1,0,0,0],
         [0,1,0,0],
         [0,0,1,0],
         [0,0,0,1],
         [1,1,0,0],
         [1,0,1,0],
         [1,0,0,1],
         [1,1,1,0],
         [1,1,0,1],
         [1,1,1,1],
         [0,0,1,1]],
        dtype=tf.float32)
    
    projector_v_encoded = tf.math.mod(tf.reshape(tf.matmul(projector_v_encoding_matrix, projector_v[:,tf.newaxis]),[11]),2)
    input_sign = 2 * (projector_v_encoded - 0.5) # 0->-1 and 1->1

    layer_1_weights = gamma[0]
    layer_1_bias = gamma[1]
    layer_2_weights = gamma[2]
    layer_2_bias = gamma[3]
    layer_1_out = tf.matmul(layer_1_weights, tf.cast(input_sign[:, tf.newaxis], tf.float32))+ layer_1_bias
    layer_1_out_act = tf.tanh(layer_1_out)
    layer_2_out = tf.matmul(layer_2_weights, layer_1_out_act) + layer_2_bias
    layer_2_out_act = tf.sigmoid(layer_2_out)
    output = tf.squeeze(layer_2_out_act, axis=1) * 0.0 # one can multiply this with a scalar, giving weights for output getting from different methods
    
    
    ones = tf.ones([2*11,1], dtype=tf.float32)
    input_encoder = tf.constant([-1,1], dtype=tf.float32)
    input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
    theta_out = tf.reshape(tf.matmul(gamma[4], input_en), [8*3])
    output = output + theta_out
    
    ones = tf.ones([2*11,1], dtype=tf.float32)
    input_encoder = tf.constant([-1,1], dtype=tf.float32)
    input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
    theta_out = tf.reshape(tf.matmul(gamma[5], input_en), [8*3])
    output = output + theta_out
    
    ones = tf.ones([2*11,1], dtype=tf.float32)
    input_encoder = tf.constant([-1,1], dtype=tf.float32)
    input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
    theta_out = tf.reshape(tf.matmul(gamma[6], input_en), [8*3]) 
    output = output + theta_out
    return output
g_func_batch_wo_grad_vmap = tc.backend.vmap(g_func_batch_wo_grad, vectorized_argnums=(0,1,))

def g_func_rounds(gamma, projector_v, CNOT_Ops, masks, n):
    # m = n
    m = 4
    assert projector_v.shape[0] == m
    
    
    with tf.GradientTape() as tape:
        tape.watch(gamma)
        projector_v_encoding_matrix = tf.constant(
        [[1,0,0,0],
         [0,1,0,0],
         [0,0,1,0],
         [0,0,0,1],
         [1,1,0,0],
         [1,0,1,0],
         [1,0,0,1],
         [1,1,1,0],
         [1,1,0,1],
         [1,1,1,1],
         [0,0,1,1]],
        dtype=tf.float32)
    
        projector_v_encoded = tf.math.mod(tf.reshape(tf.matmul(projector_v_encoding_matrix, projector_v[:,tf.newaxis]),[11]),2)
        input_sign = 2 * (projector_v_encoded - 0.5) # 0->-1 and 1->1
        # output_sign = tf.concat([tf.ones([n,1], dtype=tf.float32),input_sign[:,tf.newaxis],input_sign[:,tf.newaxis],tf.ones([n,1], dtype=tf.float32),tf.ones([n,1], dtype=tf.float32),tf.ones([n,1], dtype=tf.float32)],axis=1) # if 0, e^(-jtheta[2]/2) rx(theta[0]+theta[1]) if 1, e^(jtheta[2]/2) rx(theta[0]-theta[1])

        layer_1_weights = gamma[0]
        layer_1_bias = gamma[1]
        layer_2_weights = gamma[2]
        layer_2_bias = gamma[3]
        layer_1_out = tf.matmul(layer_1_weights, tf.cast(input_sign[:, tf.newaxis], tf.float32)) + layer_1_bias
        layer_1_out_act = tf.tanh(layer_1_out)
        layer_2_out = tf.matmul(layer_2_weights, layer_1_out_act) + layer_2_bias
        layer_2_out_act = tf.sigmoid(layer_2_out)
        output = tf.squeeze(layer_2_out_act, axis=1) * 0.0#TODO: we can multiply this with a scalar, giving weights for output getting from different methods
        
        
        ones = tf.ones([2*11,1], dtype=tf.float32)
        input_encoder = tf.constant([-1,1], dtype=tf.float32)
        input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
        theta_out = tf.reshape(tf.matmul(gamma[4], input_en), [8*3])
        output = output + theta_out
        
        ones = tf.ones([2*11,1], dtype=tf.float32)
        input_encoder = tf.constant([-1,1], dtype=tf.float32)
        input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
        theta_out = tf.reshape(tf.matmul(gamma[5], input_en), [8*3])
        output = output + theta_out
        
        ones = tf.ones([2*11,1], dtype=tf.float32)
        input_encoder = tf.constant([-1,1], dtype=tf.float32)
        input_en = (ones + tf.cast(tf.reshape(input_encoder * input_sign[:, tf.newaxis], [2*11,1]), tf.float32))/2
        theta_out = tf.reshape(tf.matmul(gamma[6], input_en), [8*3]) 
        output = output + theta_out
        
        gamma_gfunc_grad_tensor_list = tape.jacobian(output, gamma) # squeeze for output theta_2_num, 1, gamma_shape --> theta_2_num, gamma_shape TODO:check gradient
    return output, gamma_gfunc_grad_tensor_list
g_func_rounds_vmap = tc.backend.vmap(g_func_rounds, vectorized_argnums=(1,)) # TODO: really don't understand why can't jit this function


def g_func_batched_round(gamma, projector_batched_round, CNOT_Ops, masks, n): # gamma is a list of tensors
    theta_2_round, gamma_gfunc_grad_tensor_list_round = g_func_rounds_vmap(gamma, projector_batched_round, CNOT_Ops, masks, n)
    return theta_2_round, gamma_gfunc_grad_tensor_list_round
g_func_batched_round_vmap = tc.backend.jit(tc.backend.vmap(g_func_batched_round, vectorized_argnums=(0,1,)))


def Hamiltonian(c: tc.Circuit, h: float = 0):
    e = 0.0
    e += (1-h) * tf.cast(c.expectation_ps(z=[6, 1, 0, 2]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(z=[7, 0, 1, 3]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(z=[2, 5, 4, 6]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(z=[3, 4, 5, 7]), tf.float64)
    
    e += (1-h) * tf.cast(c.expectation_ps(x=[0, 2, 3, 4]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(x=[1, 3, 2, 5]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(x=[4, 6, 7, 0]), tf.float64)
    e += (1-h) * tf.cast(c.expectation_ps(x=[5, 7, 6, 1]), tf.float64)
    
    for i in range(8):
        e += h * tf.cast(c.expectation_ps(y=[i]), tf.float64)
        
    return -tc.backend.real(e)



def get_prob(n, theta_1, projector_onehot, prob_idx):
    # projector: 2 for id, 0 for 0_projector, 1 for 1_projector
    # since logical operations are unfriendly for jit, use one hot in replacement of 'if'
    # m = n
    m = 4
    theta_1 = tf.cast(theta_1, ctype,)
    circuit = U1(n, theta_1)
    projector_onehot = tf.cast(projector_onehot, ctype,)
    projector_set = tf.cast(tf.constant([[[1., 0.],[0., 0.]], [[0., 0.], [0., 1.]], [[1., 0.], [0., 1.]]]), ctype,)
    for idx in range(m):
        projector_unitary = tf.reduce_sum(projector_set * projector_onehot[idx][:, tf.newaxis, tf.newaxis], axis=-3 )# batch dimension of projector_onehot should be handled by vmap
        circuit.any(n+idx, unitary = projector_unitary)
    prob_0_uncond = circuit.expectation_ps(z=[n+prob_idx])
    return tc.backend.real(prob_0_uncond)
# get_prob_vmap = tc.backend.jit(tc.backend.vmap(get_prob, vectorized_argnums=(1, 2,))) 
get_prob_vmap = tc.backend.vmap(get_prob, vectorized_argnums=(1, 2,))


def get_prob_1(n, theta_1, projector_onehot, prob_idx):
    # projector: 2 for id, 0 for 0_projector, 1 for 1_projector
    # since logical operations are unfriendly for jit, use one hot in replacement of 'if'
    # m = n
    m = 4
    theta_1 = tf.cast(theta_1, ctype,)
    circuit = U1(n, theta_1)
    projector_onehot = tf.cast(projector_onehot, ctype,)
    projector_set = tf.cast(tf.constant([[[1., 0.],[0., 0.]], [[0., 0.], [0., 1.]], [[1., 0.], [0., 1.]]]), ctype,)
    for idx in range(m):
        projector_unitary = tf.reduce_sum(projector_set * projector_onehot[idx][:, tf.newaxis, tf.newaxis], axis=-3 )# batch dimension of projector_onehot should be handled by vmap
        circuit.any(n+idx, unitary = projector_unitary)
    pdb.set_trace()
    prob_0_uncond = circuit.expectation_ps(z=[n+prob_idx])
    return tc.backend.real(prob_0_uncond)

def adaptive_vqe(n, theta_1, theta_2, projector_onehot, sample_cond_prob, h):
    # m = n
    m = 4
    theta_1 = tf.cast(theta_1, ctype,)
    circuit = U1(n, theta_1)
    theta_2 = tf.cast(theta_2, ctype,) # since theta_2 is from classical function, its type is float32, but complex128 is needed for quantum circuit construction
    projector_onehot = tf.cast(projector_onehot, ctype,)
    projector_set = tf.cast(tf.constant([[[1., 0.], [0., 0.]], [[0., 0.], [0., 1.]], [[1., 0.], [0., 1.]]]), ctype,)
    for idx in range(m):
        projector_unitary = tf.reduce_sum(projector_set * projector_onehot[idx][:, tf.newaxis, tf.newaxis], axis=-3)# batch 
        circuit.any(n+idx, unitary = projector_unitary)
    circuit.append(U2(n, theta_2))
    energy = Hamiltonian(circuit, h)/tf.cast(sample_cond_prob, tf.float64) # the condition here is important, since what we are calculating at last is the expectation value, namely, \sum_v <ψ_v|H|ψ_v>/<ψ_v|ψ_v> and <ψ_v|ψ_v> is the conditional prob of getting this sample result v.
    return energy
adaptive_vqe_vmap = tc.backend.jit(tc.backend.vmap(adaptive_vqe, vectorized_argnums=(1, 2, 3, 4)))
# adaptive_vqe_vmap_vmap = tc.backend.jit(tc.backend.vmap(adaptive_vqe_vmap, vectorized_argnums=(2, 3,))) # adding round dimension fot theta_2 and projector


def sample(n, batch_size, theta_1_batched):
    # m = n
    m = 4
    prob_batched = tf.zeros([batch_size, m, 2])
    projector_batched = 2 * tf.ones([batch_size, m]) # 2 for Identity
    cond_prob_batched = tf.ones(batch_size)
    for idx in range(m):
        if(idx > 0):
            logits = tf.math.log(prob_batched[:,idx-1])
            projector_batched = tf.transpose(tf.tensor_scatter_nd_update(tf.transpose(projector_batched), indices=tf.constant([[idx-1]]), updates=tf.cast(tf.reshape(tf.random.categorical(logits, 1),(1, batch_size)), dtype=tf.float32)))
            
            cond_prob_batched = tf.reduce_sum(tf.reshape(cond_prob_batched, shape=(batch_size, 1)) * (prob_batched[:,idx-1] * tf.one_hot(tf.cast(projector_batched[:, idx-1], dtype=tf.int64), 2, dtype=tf.float32)), axis=-1)
            
        
        projector_batched = tf.transpose(tf.tensor_scatter_nd_update(tf.transpose(projector_batched), indices=tf.constant([[idx]]), updates=tf.cast(tf.reshape(tf.zeros([1,batch_size]),(1, batch_size)), dtype=tf.float32)))# this is important for getting the actual probability of having 0 as measurement outcome!!
        
        projector_batched_onehot = tf.one_hot(tf.cast(projector_batched, dtype=tf.int64), 3) # batch_size, m, 3
        prob_0_uncond = get_prob_vmap(n, theta_1_batched, projector_batched_onehot, idx)
        prob_0 = tf.cast(prob_0_uncond, tf.float32)/cond_prob_batched
        prob_batched = tf.transpose(tf.tensor_scatter_nd_update(tf.transpose(prob_batched, perm=[1,2,0]), indices=tf.constant([[[idx, 0], [idx, 1]]]), updates=tf.concat([prob_0[tf.newaxis, :], (1 - prob_0)[tf.newaxis,:]], axis=0)[tf.newaxis, :]), perm=[2,0,1])
        
    logits = tf.math.log(prob_batched[:,-1])
    projector_batched = tf.transpose(tf.tensor_scatter_nd_update(tf.transpose(projector_batched), indices=tf.constant([[m-1]]), updates=tf.cast(tf.reshape(tf.random.categorical(logits, 1),(1, batch_size)), dtype=tf.float32)))
    
    cond_prob_batched = tf.reduce_sum(tf.reshape(cond_prob_batched, shape=(batch_size, 1)) * (prob_batched[:,m-1] * tf.one_hot(tf.cast(projector_batched[:, m-1], dtype=tf.int64), 2, dtype=tf.float32)), axis=-1) 
    
    return projector_batched, cond_prob_batched


sample_vmap = tc.backend.jit(tc.backend.vmap(sample, vectorized_argnums=(2,))) #vectorize the round dime
    
    
def grad_theta_1_paramshift_sample(n, theta_1_batched_round, gamma_batched,  CNOT_Ops, masks, batch_size, sample_round, h):
    # theta_1_batched_round list of tensors(theta_1_batched) same with theta_2 # need parallel sampling
    # theta_1_batched_round shape: sample_round, batch_size, theta_2_num
    m = 4
    gamma_batched_tiled = []
    for i in range(len(gamma_batched)):
        gamma_batched_tiled.append(tf.tile(gamma_batched[i], [int(16*3),1,1])) # theta_1_num * batch_size, input_feature, output_feature
        
    theta_1_batched_r_b = tf.cast(tf.tile(theta_1_batched_round[:, :, tf.newaxis, :], [1, 1, int(16*3), 1]), tf.float32) # shape sample_round, batch_size, param_theta_1_num, param_theta_1_num
    shift_tensor_one_batch = np.pi/2 * tf.eye(int(16*3))
    shift_tensor = tf.cast(tf.tile(shift_tensor_one_batch[tf.newaxis, tf.newaxis, :, :], [sample_round, batch_size, 1, 1]), tf.float32)
    theta_1_pos_batched_tf = theta_1_batched_r_b + shift_tensor
    theta_1_pos_batched_tf = tf.transpose(theta_1_pos_batched_tf, perm=[0,2,1,3]) # round, theta_1_num, batch, num_theta_1(in each batch, shift same theta_idx)
    theta_1_pos_batched_tf_r_theta1_b_theta1 = tf.transpose(theta_1_pos_batched_tf, perm=[1,0,2,3]) # theta_1_num, round, batch, num_theta_1 (for later adaptive_vqe_vmap use)
    theta_1_pos_batched_tf_r_theta1_b_theta1 = tf.reshape(theta_1_pos_batched_tf_r_theta1_b_theta1, [int(16*3 * sample_round*batch_size), int(16*3)]) # theta_1_num*round*batch, num_theta_1 (for later adaptive_vqe_vmap use)
    theta_1_pos_batched_tf = tf.reshape(theta_1_pos_batched_tf, [int(sample_round * 16*3), batch_size, int(16*3)]) # round*theta_1_num, batch_size, theta_1_num (though same shape with above, but are different! see the order of multiplication for the first dimension)
    projector_pos, cond_prob_batched_pos = sample_vmap(n, batch_size, theta_1_pos_batched_tf) # projector_pos: round*theta_1_num, batch_size, v; cond_prob_batched_pos: round*theta_1_num, batch_size
    projector_pos = tf.reshape(projector_pos, [sample_round, int(16*3), batch_size, m]) # round, theta_1_num, batch_size, v
    projector_pos = tf.transpose(projector_pos, [1,0,2,3]) # theta_1_num, sample_round, batch_size, v
    
    cond_prob_batched_pos = tf.reshape(cond_prob_batched_pos[:, :, tf.newaxis], [sample_round, int(16*3), batch_size, 1]) # round, theta_1_num, batch_size, 1
    cond_prob_batched_pos = tf.transpose(cond_prob_batched_pos, [1,0,2,3]) # theta_1_num, round, batch_size, 1
    cond_prob_batched_pos = tf.reshape(cond_prob_batched_pos, [sample_round*int(16*3)*batch_size, 1]) # theta_1_num*round*batch_size, 1
    projector_pos_onehot = tf.one_hot(tf.cast(projector_pos, tf.int64), 3) # theta_1_num, sample_round, batch_size, v, 3
    projector_pos_onehot = tf.reshape(projector_pos_onehot, [int(16*3 * sample_round*batch_size), m, 3]) # theta_1_num*sample_round*batch_size, v, 3
    projector_pos = tf.transpose(projector_pos, [0,2,1,3]) # theta_1_num, batch_size, sample_round, v
    projector_pos = tf.reshape(projector_pos, [int(16*3 * batch_size), sample_round, m]) # theta_1_num*batch_size, sample_round, v
    theta_2_pos1_batched, _ = g_func_batched_round_vmap(gamma_batched_tiled, projector_pos, CNOT_Ops, masks, n) # theta_1_num*batch_size, sample_round, theta_2_num
    theta_2_pos1_b_r = tf.reshape(theta_2_pos1_batched, [int(16*3), batch_size, sample_round, int(8*3)]) # theta_1_num, batch_size, sample_round, theta_2_num
    theta_2_pos1_r_b = tf.transpose(theta_2_pos1_b_r, [0,2,1,3]) # theta_1_num, sample_round, batch_size, theta_2_num
    theta_2_pos1_r_b = tf.reshape(theta_2_pos1_r_b, [int(16*3 * sample_round*batch_size), int(8*3)]) # theta_1_num*sample_round*batch_size, theta_2_num
    
    energy_pos = adaptive_vqe_vmap(n, theta_1_pos_batched_tf_r_theta1_b_theta1, theta_2_pos1_r_b, projector_pos_onehot, cond_prob_batched_pos, h) # theta_1_num*sample_round*batch_size
    
    
    theta_1_neg_batched_tf = theta_1_batched_r_b - shift_tensor
    theta_1_neg_batched_tf = tf.transpose(theta_1_neg_batched_tf, perm=[0,2,1,3]) # round, theta_1_num, batch, num_theta_1(in each batch, shift same theta_idx)
    theta_1_neg_batched_tf_r_theta1_b_theta1 = tf.transpose(theta_1_neg_batched_tf, perm=[1,0,2,3]) # theta_1_num, round, batch, num_theta_1 (for later adaptive_vqe_vmap use)
    theta_1_neg_batched_tf_r_theta1_b_theta1 = tf.reshape(theta_1_neg_batched_tf_r_theta1_b_theta1, [int(16*3 * sample_round*batch_size), int(16*3)]) # theta_1_num*round*batch, num_theta_1 (for later adaptive_vqe_vmap use)
    theta_1_neg_batched_tf = tf.reshape(theta_1_neg_batched_tf, [int(sample_round * 16*3), batch_size, int(16*3)]) # round*theta_1_num, batch_size, theta_1_num (though same shape with above, but are different! see the order of multiplication for the first dimension)
    
    projector_neg, cond_prob_batched_neg = sample_vmap(n, batch_size, theta_1_neg_batched_tf) # projector_neg:round*theta_1_num, batch_size, v; cond_prob_batched_neg: round*theta_1_num, batch_size
    cond_prob_batched_neg = tf.reshape(cond_prob_batched_neg[:, :, tf.newaxis], [sample_round, int(16*3), batch_size, 1]) # round, theta_1_num, batch_size, 1
    cond_prob_batched_neg = tf.transpose(cond_prob_batched_neg, [1,0,2,3]) # theta_1_num, round, batch_size, 1
    cond_prob_batched_neg = tf.reshape(cond_prob_batched_neg, [sample_round*int(16*3)*batch_size, 1]) # theta_1_num*round*batch_size, 1
    
    
    projector_neg = tf.reshape(projector_neg, [sample_round, int(16*3), batch_size, m]) # round, theta_1_num, batch_size, v
    projector_neg = tf.transpose(projector_neg, [1,0,2,3]) # theta_1_num, sample_round, batch_size, v
    projector_neg_onehot = tf.one_hot(tf.cast(projector_neg, tf.int64), 3) # theta_1_num, sample_round, batch_size, v, 3
    projector_neg_onehot = tf.reshape(projector_neg_onehot, [int(16*3 * sample_round*batch_size), m, 3]) # theta_1_num*sample_round*batch_size, v, 3
    projector_neg = tf.transpose(projector_neg, [0,2,1,3]) # theta_1_num, batch_size, sample_round, v
    projector_neg = tf.reshape(projector_neg, [int(16*3 * batch_size), sample_round, m]) # theta_1_num*batch_size, sample_round, v
    theta_2_neg1_batched, _ = g_func_batched_round_vmap(gamma_batched_tiled, projector_neg, CNOT_Ops, masks, n) # theta_1_num*batch_size, sample_round, theta_2_num
    theta_2_neg1_b_r = tf.reshape(theta_2_neg1_batched, [int(16*3), batch_size, sample_round, int(8*3)]) # theta_1_num, batch_size, sample_round, theta_2_num
    theta_2_neg1_r_b = tf.transpose(theta_2_neg1_b_r, [0,2,1,3]) # theta_1_num, sample_round, batch_size, theta_2_num
    theta_2_neg1_r_b = tf.reshape(theta_2_neg1_r_b, [int(16*3 * sample_round*batch_size), int(8*3)]) # theta_1_num*sample_round*batch_size, theta_2_num
    energy_neg = adaptive_vqe_vmap(n, theta_1_neg_batched_tf_r_theta1_b_theta1, theta_2_neg1_r_b, projector_neg_onehot, cond_prob_batched_neg, h) # theta_1_num*sample_round*batch_size
    
    grad_theta_1_round = 0.5 * (energy_pos - energy_neg) # theta_1_num*sample_round*batch_size
    grad_theta_1_round = tf.cast(tf.reshape(grad_theta_1_round, [int(16*3), sample_round, batch_size]), tf.float32) # theta_1_num, sample_round, batch_size
    grad_theta_1 = tf.reduce_mean(grad_theta_1_round, axis=1) # theta_1_num, batch_size
    grad_theta_1 = tf.transpose(grad_theta_1, perm=[1,0]) # batch_size, theta_1_num
    return grad_theta_1
grad_theta_1_paramshift_sample_jit = tc.backend.jit(grad_theta_1_paramshift_sample)
    
    
def grad_theta_2_paramshift(n, theta_1_batched, theta_2_batched_round, projector_v_onehot_round, cond_prob_batched, batch_size, sample_round, h):
    m = 4
    # projector_v_onehot_round_tf # sample_round, batch_size, v, 3
    # theta_2_batched_round: sample_round, batch_size, theta_2_num
    # cond_prob_batched: round, batch_size
    projector_v_onehot_round_tf = tf.tile(projector_v_onehot_round[tf.newaxis, :, :, :, :], [int(8*3), 1, 1, 1, 1]) # theta_2_num, sample_round, batch_size, v, 3
    projector_v_onehot_round_tf = tf.transpose(projector_v_onehot_round_tf, [1,0,2,3,4]) # sample_round, theta_2_num, batch_size, v, 3
    projector_v_onehot_tf = tf.reshape(projector_v_onehot_round_tf, [int(sample_round * (8*3) * batch_size), m, 3])
    
    theta_1_batched_tf = tf.tile(theta_1_batched[tf.newaxis, tf.newaxis, :], [sample_round, int(8*3), 1, 1]) # sample_round, theta_2_num, batch_size, theta_1_num
    theta_1_batched_tf = tf.reshape(theta_1_batched_tf, [int(sample_round * (8*3) * batch_size), int(16*3)])
    
    cond_prob_batched = tf.reshape(cond_prob_batched[:, :, tf.newaxis], [sample_round, batch_size, 1]) # round, batch_size, 1
    cond_prob_batched = tf.tile(cond_prob_batched[tf.newaxis, :, :, :], [int(8*3), 1, 1, 1]) # theta_2_num, round, batch_size, 1
    cond_prob_batched = tf.transpose(cond_prob_batched, [1,0,2,3]) # round, theta_2_num, batch_size, 1
    cond_prob_batched = tf.reshape(cond_prob_batched, [int(sample_round * (8*3) * batch_size), 1]) # round*theta_2_num*batch_size, 1
        
    
    # theta_2_batched_round shape: sample_round, batch_size, theta_2_num
    theta_2_batched_r_b = tf.cast(tf.tile(theta_2_batched_round[:, :, tf.newaxis, :], [1, 1, int(8*3), 1]), tf.float32) # shape sample_round, batch_size, param_theta_2_num, param_theta_2_num
    shift_tensor_one_batch = np.pi/2 * tf.eye(int(8*3))
    shift_tensor = tf.cast(tf.tile(shift_tensor_one_batch[tf.newaxis, tf.newaxis, :, :], [sample_round, batch_size, 1, 1]), tf.float32)
    theta_2_pos_batched_tf = theta_2_batched_r_b + shift_tensor
    theta_2_pos_batched_tf = tf.transpose(theta_2_pos_batched_tf, perm=[0,2,1,3]) # round, theta_2_num, batch, num_theta_2(in each batch, shift same theta_idx)
    theta_2_pos_batched_tf = tf.reshape(theta_2_pos_batched_tf, [int(sample_round * (8*3) * batch_size), int(8*3)])
    
    energy_pos = adaptive_vqe_vmap(n, theta_1_batched_tf, theta_2_pos_batched_tf, projector_v_onehot_tf, cond_prob_batched, h)
    
    theta_2_neg_batched_tf = theta_2_batched_r_b - shift_tensor
    theta_2_neg_batched_tf = tf.transpose(theta_2_neg_batched_tf, perm=[0,2,1,3]) # round, theta_2_num, batch, num_theta_2(in each batch, shift same theta_idx)
    theta_2_neg_batched_tf = tf.reshape(theta_2_neg_batched_tf, [int(sample_round * (8*3) * batch_size), int(8*3)])
    energy_neg = adaptive_vqe_vmap(n, theta_1_batched_tf, theta_2_neg_batched_tf, projector_v_onehot_tf, cond_prob_batched, h)
    
    theta_2_grad = 0.5 * (energy_pos - energy_neg) # sample_round*theta_2_num*batch_size
    theta_2_grad = tf.reshape(theta_2_grad, [sample_round, int(8*3), batch_size]) # sample_round, theta_2_num, batch_size
    return theta_2_grad
grad_theta_2_paramshift_jit = tc.backend.jit(grad_theta_2_paramshift)
    
    
    

def train(n: int, init_theta_1_batched: tf.Variable, init_gamma_batched: tf.Variable, CNOT_Ops: list, masks: list,  batch_size: int, h: float,  optimizer: tf.keras.optimizers, sample_round: int, max_iter: int, record: int):
    theta_1_batched = init_theta_1_batched # should be tf.Variable
    gamma_batched = init_gamma_batched # should be tf.Variable
    energy_batched_record = []
    energy_min_record = []
    theta_1_batched_record = []
    gamma_batched_record = []
    for iter in range(max_iter):
        start = time.time()
        theta_1_batched_round = tf.tile(theta_1_batched[tf.newaxis, :, :], [sample_round, 1, 1]) # sample_round, batch, theta_1_num
        projector_v_batched_round_r_b, cond_prob_batched = sample_vmap(n, batch_size, theta_1_batched_round) # projector_v_batched_round_r_b: sample_round, batch, v; cond_prob_batched: sample_round, batch
        
        projector_v_batched_round_b_r = tf.transpose(projector_v_batched_round_r_b, [1,0,2])        
        projector_v_onehot_batched_round_tf = tf.one_hot(tf.cast(projector_v_batched_round_r_b, tf.int64), 3) # sample_round, batch, v, 3 ### remeber delete stack operation in grad_theta_2

        theta_2_batched_b_r, gamma_gfunc_grad_batched_list = g_func_batched_round_vmap(gamma_batched, projector_v_batched_round_b_r, CNOT_Ops, masks, n)
        # gamma_gfunc_grad_batched should be list of tensors, each tensor: batch_size, round, theta_2_num, layer_input_feature, layer_output_feature
        theta_2_batched_r_b = tf.transpose(theta_2_batched_b_r, perm=[1,0,2])
        
        grad_theta_1_batched = grad_theta_1_paramshift_sample_jit(n, theta_1_batched_round, gamma_batched,  CNOT_Ops, masks, batch_size, sample_round, h)
        grad_theta_2_round_batched = grad_theta_2_paramshift_jit(n, theta_1_batched, theta_2_batched_r_b, projector_v_onehot_batched_round_tf, cond_prob_batched, batch_size, sample_round, h)# shape round, batch, theta_2_num
        
        
        grad_gamma_batched = []
        for i in range(len(gamma_gfunc_grad_batched_list)):
            gamma_gfunc_grad_batched_list_i = tf.transpose(gamma_gfunc_grad_batched_list[i], perm=[1,0,2,3,4]) #  round, batch_size, theta_2_num, layer_input_feature, layer_output_feature
            gamma_gfunc_grad_batched_list_i = tf.transpose(gamma_gfunc_grad_batched_list_i, perm=[0,2,1,3,4]) #  round, theta_2_num, batch_size, layer_input_feature, layer_output_feature
            grad_gamma_i_batched_round = tf.reduce_sum(gamma_gfunc_grad_batched_list_i * tf.cast(grad_theta_2_round_batched[:, :, :, tf.newaxis, tf.newaxis], tf.float32), axis=1) # round, batch_size, layer_input_feature, layer_output_feature
            grad_gamma_i_batched = tf.cast(tf.reduce_mean(grad_gamma_i_batched_round, axis=0), tf.float32)
            grad_gamma_batched.append(grad_gamma_i_batched)
            
        if (iter%record)==0:
            # for energy record calculation
            theta_1_batched_round_for_record = tf.reshape(theta_1_batched_round, [int(sample_round*batch_size), theta_1_batched_round.shape[2]])
            theta_2_batched_r_b_for_record = tf.reshape(theta_2_batched_r_b, [int(sample_round*batch_size), theta_2_batched_r_b.shape[2]])
            projector_v_onehot_batched_round_tf_for_record = tf.reshape(projector_v_onehot_batched_round_tf, [sample_round*batch_size, projector_v_onehot_batched_round_tf.shape[2], projector_v_onehot_batched_round_tf.shape[3]])
            cond_prob_batched_for_record = tf.reshape(cond_prob_batched[:, :, tf.newaxis], [sample_round*batch_size, 1])
            
            energy_record_round_batched = adaptive_vqe_vmap(n, theta_1_batched_round_for_record, theta_2_batched_r_b_for_record, projector_v_onehot_batched_round_tf_for_record, cond_prob_batched_for_record, h) # sample_round*batch_size
            energy_record_round_batched = tf.reshape(energy_record_round_batched, [int(sample_round), int(batch_size)]) # sample_round, batch_size
            energy_record_batched_ave = tf.reduce_mean(energy_record_round_batched, axis=0) # batch_size
            
            theta_2_batched = g_func_batch_wo_grad_vmap(gamma_batched, projector_v_batched_round_r_b[0,:], CNOT_Ops, masks, n)
        optimizer.apply_gradients(zip(grad_gamma_batched, gamma_batched))
        optimizer.apply_gradients(zip([grad_theta_1_batched], [theta_1_batched])) # need to be list of tensor(s)
        
        
        
        stop = time.time()
        print(f'--------- finish_iteration_{iter} time_consumption: {stop-start:.3f} ---------')
        if (iter%record)==0:            
            energy_batched_record.append(energy_record_batched_ave)
            theta_1_batched_record.append(theta_1_batched)
            gamma_batched_record.append(gamma_batched)
            energy_min_record.append(np.min(energy_record_batched_ave.numpy(), axis=0))
            print(f'current_energy(before update):\n {energy_record_batched_ave}')
            print(f'lowest_energy: {np.min(energy_record_batched_ave.numpy(), axis=0)}\n')
            
    return theta_1_batched_record, gamma_batched_record, energy_batched_record, energy_min_record, theta_2_batched
        

def he_init(shape,random_seed):
    fan_in = shape[-2]
    stddev = tf.sqrt(2.0/fan_in)
    return tf.random.normal(shape, stddev=stddev, seed=random_seed)

def param_mapping(n, m, batch_size, param_path):
    input_param = np.load(param_path)
    if(batch_size < input_param.shape[0]):
        input_param = input_param[12:12+batch_size]
    init_theta_1 = input_param[:,0:16*3]
    theta_2_1 = input_param[:,16*3:16*3+4*8*3]
    theta_2_1 = np.reshape(theta_2_1, [batch_size,4,8,3]) # [batch_size][log2(n)][n//2][3]
    theta_2_2 = input_param[:,16*3+4*8*3:16*3+4*8*3+7*8*3]
    theta_2_2 = np.reshape(theta_2_2,[batch_size,7,8,3])
    theta_2_3 = input_param[:,16*3+4*8*3+7*8*3:16*3+4*8*3+7*8*3+8*3]
    theta_2_3 = np.reshape(theta_2_3,[batch_size,8,3])

    init_gamma_4 = np.zeros([batch_size, 8*3, 2*11])
    for i in range(4):
        for j in range(8):       
            init_gamma_4[:,j*3+0,2*i] = theta_2_1[:,i,j,2] + theta_2_1[:,i,j,0] # each row represent a ancillary qubit, thus is j,i instead of i,j
            init_gamma_4[:,j*3+0,2*i+1] = theta_2_1[:,i,j,2] - theta_2_1[:,i,j,0]

    
    init_gamma_5 = np.zeros([batch_size, 8*3, 2*11])
    for i in range(7):
        for j in range(8):
            init_gamma_5[:,j*3+0,8+2*i] = theta_2_2[:,i,j,2] + theta_2_2[:,i,j,0] # each row represent a ancillary qubit, thus is j,i instead of i,j
            init_gamma_5[:,j*3+0,8+2*i+1] = theta_2_2[:,i,j,2] - theta_2_2[:,i,j,0]
            
            
    init_gamma_6 = np.zeros([batch_size, 8*3, 2*11])
    for i in range(8):
        init_gamma_6[:,3*i+0,0] = theta_2_3[:,i,0]
        init_gamma_6[:,3*i+0,1] = theta_2_3[:,i,0]
        init_gamma_6[:,3*i+1,0] = theta_2_3[:,i,1]
        init_gamma_6[:,3*i+1,1] = theta_2_3[:,i,1]
        init_gamma_6[:,3*i+2,0] = theta_2_3[:,i,2]
        init_gamma_6[:,3*i+2,1] = theta_2_3[:,i,2]
        
    return init_theta_1, init_gamma_4, init_gamma_5, init_gamma_6

    
    

def init_param(n, m, batch_size, random_seed, load_param=False, param_path=None):
    # l = int(tf.math.log(tf.cast(m, tf.float32))/tf.math.log(2.0))
    if load_param:
        print(f'params loaded from {param_path}\n')
        init_gamma_layer_1_weights = tf.Variable(initial_value=he_init([batch_size, 16*11, 11],random_seed[4]))
        init_gamma_layer_1_bias = tf.Variable(initial_value=tf.random.normal(shape=[batch_size, 16*11, 1], mean=0, stddev=0.1,seed=random_seed[5])) # the first round of g_func has input v = all zero, thus we need non_zero bias to make non-trivial output theta_2
        init_gamma_layer_2_weights = tf.Variable(initial_value=he_init([batch_size, 8*3, 16*11],random_seed[6]))
        init_gamma_layer_2_bias = tf.Variable(initial_value=tf.random.normal(shape=[batch_size, 8*3, 1], mean=0, stddev=0.1,seed=random_seed[7]))
        init_gamma = [init_gamma_layer_1_weights, init_gamma_layer_1_bias, init_gamma_layer_2_weights, init_gamma_layer_2_bias]
        init_theta_1, init_gamma_4, init_gamma_5, init_gamma_6 = param_mapping(n, m, batch_size, param_path)
        init_theta_1 = tf.Variable(initial_value=init_theta_1,dtype=tf.float32)
        init_gamma.append(tf.Variable(initial_value=init_gamma_4,dtype=tf.float32))
        init_gamma.append(tf.Variable(initial_value=init_gamma_5,dtype=tf.float32))
        init_gamma.append(tf.Variable(initial_value=init_gamma_6,dtype=tf.float32))
        
    else:
        init_theta_1 = tf.Variable(initial_value=tf.concat([
            tf.random.normal(shape=(int(batch_size/4),16*3), mean=0.0, stddev=0.2,seed=random_seed[0]),
            tf.random.normal(shape=(int(batch_size/4),16*3), mean=np.pi/2, stddev=0.2,seed=random_seed[1]),
            tf.random.normal(shape=(int(batch_size/4),16*3), mean=np.pi, stddev=0.2,seed=random_seed[2]),
            tf.random.normal(shape=(int(batch_size/4),16*3), mean=np.pi*3/2, stddev=0.2,seed=random_seed[3])
            ], axis=0))
        init_gamma_layer_1_weights = tf.Variable(initial_value=he_init([batch_size, 16*11, 11],random_seed[4]))
        init_gamma_layer_1_bias = tf.Variable(initial_value=tf.random.normal(shape=[batch_size, 16*11, 1], mean=0, stddev=0.1,seed=random_seed[5])) # the first round of g_func has input v = all zero, thus we need non_zero bias to make non-trivial output theta_2
        init_gamma_layer_2_weights = tf.Variable(initial_value=he_init([batch_size, 8*3, 16*11],random_seed[6]))
        init_gamma_layer_2_bias = tf.Variable(initial_value=tf.random.normal(shape=[batch_size, 8*3, 1], mean=0, stddev=0.1,seed=random_seed[7]))
        init_gamma = [init_gamma_layer_1_weights, init_gamma_layer_1_bias, init_gamma_layer_2_weights, init_gamma_layer_2_bias]
        init_gamma_4 = tf.Variable(initial_value=he_init([batch_size, 8*3, 2*11],random_seed[7]))
        init_gamma.append(init_gamma_4)
        init_gamma_5 = tf.Variable(initial_value=he_init([batch_size, 8*3, 2*11],random_seed[8]))
        init_gamma.append(init_gamma_5)
        init_gamma_6 = tf.Variable(initial_value=he_init([batch_size, 8*3, 2*11],random_seed[9]))
        init_gamma.append(init_gamma_6)
        init_gamma_prior_dense = tf.Variable(initial_value=he_init([batch_size, 8*3, 2*11],random_seed[10]))
        init_gamma.append(init_gamma_prior_dense)
    return init_theta_1, init_gamma 

def get_CNOT_Ops_and_masks(n):
    l = int(tf.math.log(tf.cast(n, tf.float32))/tf.math.log(2.0))
    CNOT_Ops = []
    masks = []
    mask = tf.cast(tf.reshape(tf.concat([tf.zeros([int(n/2),1]),tf.ones([int(n/2),1])],axis=1), [n,1]), tf.float32)
    masks.append(mask)
    for i in range(l-1):
        CNOT_op = tf.eye(n,n,dtype=tf.float32)
        cnot_list = []
        update_cnot = []
        mask_list = []
        update_mask = []
        for j in range(1,n-1,2**(i+1)):
            cnot_list.append([j,j+2**i]) # CNOT j+2**i-->j
            update_cnot.append(1.)
            mask_list.append([j+1])
            update_mask.append(1.)
        CNOT_op = tf.cast(tf.tensor_scatter_nd_update(CNOT_op,cnot_list,update_cnot), tf.float32)
        mask = tf.cast(tf.reshape(tf.tensor_scatter_nd_update(tf.zeros(n), mask_list, update_mask), [n,1]), tf.float32)
        CNOT_Ops.append(CNOT_op)
        masks.append(mask)
    return CNOT_Ops, masks


if __name__ == '__main__':
    n = 8
    m = 4
    # kx = 4
    h = 0
    batch_size = 16
    sample_round = 100
    max_iter = 1000
    record = 1
    rand_seed = 2232119
    np.random.seed(rand_seed)
    rand_seed_array = np.random.randint(1,100000,size=[11,20])
    load_param_max_iter = 300
    record_round = 0
    
    CNOT_Ops, masks = get_CNOT_Ops_and_masks(n)
    
    best_results = []
    h_range = np.arange(0,1.1,0.1)
    
    for i in np.arange(1):
        h = 0.1*i + 0.1
        
        initial_learning_rate = 1e-3
        decay_steps = 100
        decay_rate = 0.9
        lr_schedule = tf.keras.optimizers.schedules.ExponentialDecay(
            initial_learning_rate=initial_learning_rate,
            decay_steps=decay_steps,
            decay_rate=decay_rate
            )
        optimizer = tf.keras.optimizers.legacy.Adam(learning_rate=lr_schedule)
        param_path = f'./results/toric/toric_trail_1_x_preserving_seed={int(rand_seed)}_iter={int(load_param_max_iter)}_trained_Feb24/params_Y/Y_h={h}.npy'
        init_theta_1_batched, init_gamma_batched = init_param(n, m, batch_size, random_seed=rand_seed_array[i], load_param=True, param_path=param_path)
        theta_1_batched_record, gamma_batched_record, energy_batched_record, energy_min_record, theta_2_batched = train(n, init_theta_1_batched, init_gamma_batched, CNOT_Ops, masks, batch_size, h, optimizer, sample_round, max_iter, record)
        np.save(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/params_Y/theta_1_batched_Y_h={h}.npy',theta_1_batched_record[-1])
        np.save(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/params_Y/theta_2_batched_Y_h={h}.npy', theta_2_batched)
        for i in range(len(gamma_batched_record[-1])):
            np.save(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/params_Y/gamma_batched_{i}_Y_h={h}.npy',np.array(gamma_batched_record[-1][i]))
        
        
        np.save(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/results_Y/energy_min_record_Y_h={h}.npy', energy_min_record)
        best_results.append(np.min(energy_min_record))
        plt.figure()
        plt.plot(energy_min_record)
        plt.xlabel('iter')
        plt.ylabel('energy')
        # plt.show()
        plt.savefig(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/results_Y/Y_h={h}.jpg')
        
    np.save(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/results_Y/best_results_Y.npy', best_results)
    plt.figure()
    plt.plot(0.1*np.arange(11), best_results)
    plt.xlabel('h_Y')
    plt.ylabel('energy')
    plt.savefig(f'./results/toric/toric_trail_seed={int(rand_seed)}_load_iter={int(load_param_max_iter)}_NN_iter={int(max_iter)}_NNweight=0.1_load_params_Y_x_preserving_Feb23_record_round={record_round}/results_Y/best_results_Y.jpg')
