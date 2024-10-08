# LOCC-VQE

This is the Python-based repository for [*Variational LOCC-assisted quantum circuits for long-range entangled states*](https://arxiv.org/abs/2409.07281). [Tensorcircuit](https://github.com/tencent-quantum-lab/tensorcircuit), [Tensorflow](https://www.tensorflow.org/), and [JAX](https://jax.readthedocs.io/en/latest/index.html) are used.

### LOCC-VQE scheme
<div style="text-align:center;">
<p>
    <img src="https://drive.google.com/uc?id=176-sJldgp4Quu2OCXo9Jtr8KNJB0tJyd">
</p>
</div>
<p>
    <em><b>LOCC-VQE scheme.</b> Blue blocks represent unitary circuits, and orange blocks represent mid-circuit measurements.  <b>(a)</b> Algorithm structure of LOCC-VQE. Gradient information is obtained for optimizing the LOCC parameters &gamma; in the feedback loop, represented by the red arrow. This feedback loop is the main difference from variational quantum algorithms.  <b>(b)</b> Exploring the Hilbert space with LOCC-VQE. Among all possible paths, represented by dash arrows, agents obtained the gradient information to find an optimized state preparation path, represented by solid arrows, to reach the target state. LOCC enables states to jump in the Hilbert space, breaking the light cone limitation on unitary circuits, as illustrated by the dotted yellow circles. <b>(c)</b> Variational LOCC-assisted quantum circuits. Parameterized unitary layers, represented in blue, and mid-circuit measurement layers, represented in orange, are applied alternatively.</em>
</p>

Please check our paper [*Variational LOCC-assisted quantum circuits for long-range entangled states*](https://arxiv.org/abs/2409.07281) for more details.

## About this repository
### Features
  - Training LOCC-VQE.
  - Training sample-based LOCC-VQE with neural networks and lookup tables as LOCC functions.
  - Training with unitary VQE.
  - Calculate quantum mutual information and correlation of the results.

### Physical models
  - Perturbed Greenberger–Horne–Zeilinger state.
  - Transverse-field Ising model.
  - Perturbed rotated surface code.
  - Perturbed toric code.




