'''
Trains a simple convet on a mixture of real MNIST data
and fake generated data

'''

from keras.datasets import mnist
import theano
import theano.tensor as T
import lasagne
import numpy as np
import time
from functools import partial
import pdb

img_rows, img_cols = 28,28 # Input image dimensions
batch_size = 128
nb_classes = 2
nb_epoch = 12
nb_filters = 32 # Number of convolution filters
pool_size = (2,2)
kernel_size = (3,3)


def load_dataset():
    # Load the data
    #    X_training, X_testing, input_shape = load_dataset()
    #    y_training = np.ones((len(X_training), 1))
    #    y_testing = np.ones((len(X_testing), 1))

    (X_train, y_train), (X_test, y_test) = mnist.load_data()
    X_train = X_train.astype('float32')
    X_test = X_test.astype('float32')
    X_train /= 255
    X_test /= 255

    X_train = X_train.reshape(-1, 1, img_rows, img_cols)
    #    y_train = X_train.reshape(-1, 1, img_rows, img_cols)
    X_test = X_test.reshape(-1, 1, img_rows, img_cols)
    #    y_test = X_train.reshape(-1, 1, img_rows, img_cols)

    # We reserve the last 10000 training examples for validation.
    X_train, X_val = X_train[:-10000], X_train[-10000:]
    y_train, y_val = y_train[:-10000], y_train[-10000:]

    y_train = np.ones(y_train.shape).astype('int32')
    y_test = np.ones(y_test.shape).astype('int32')
    y_val = np.ones(y_val.shape).astype('int32')

    return (X_train, y_train, X_test,y_test, X_val, y_val)

def classifier(input_var=None):
    network = lasagne.layers.InputLayer(shape=(None, 1, img_rows, img_cols),
                                        input_var=input_var)
    network = lasagne.layers.Conv2DLayer(
            network, num_filters=nb_filters, filter_size=kernel_size,
            nonlinearity=lasagne.nonlinearities.rectify,
            W=lasagne.init.GlorotUniform())
    network = lasagne.layers.MaxPool2DLayer(network, pool_size=pool_size)
    network = lasagne.layers.Conv2DLayer(
            network, num_filters=nb_filters, filter_size=kernel_size,
            nonlinearity=lasagne.nonlinearities.rectify)
    network = lasagne.layers.MaxPool2DLayer(network, pool_size=pool_size)
    network = lasagne.layers.DenseLayer(
            lasagne.layers.dropout(network, p=.25),
            num_units=128,
            nonlinearity=lasagne.nonlinearities.rectify)

    network = lasagne.layers.DenseLayer(
            lasagne.layers.dropout(network, p=.5),
            num_units=nb_classes,
            nonlinearity=lasagne.nonlinearities.softmax)

    network = lasagne.layers.ReshapeLayer(network, (-1, nb_classes))

    return network


def synthesiser(input_var=None):

    #    https://gist.github.com/f0k/738fa2eedd9666b78404ed1751336f56

    network = lasagne.layers.InputLayer(shape=(None, 128, 1, 1), input_var=input_var)
    network = lasagne.layers.Upscale2DLayer(network, scale_factor=98, mode='repeat')
    print(lasagne.layers.get_output_shape(network))
    network = lasagne.layers.ReshapeLayer(network, (-1, 256, 7, 7))
    network = lasagne.layers.Deconv2DLayer(
        incoming=network,
        num_filters=nb_filters,
        filter_size=kernel_size,
        stride=2,
        nonlinearity=lasagne.nonlinearities.rectify
        )

    network = lasagne.layers.Deconv2DLayer(
        incoming=network,
        num_filters=nb_filters,
        filter_size=kernel_size,
        stride=2,
        nonlinearity=lasagne.nonlinearities.rectify
   )

    print(lasagne.layers.get_output_shape(network))
    network = lasagne.layers.ReshapeLayer(network, (-1, 1, img_rows, img_cols))

    return network


def mixin(batch, GenFunc):
    # This function transforms some real images into those generated by the genertor function
    inputs, targets = batch
    assert len(inputs) == len(targets)
#    assert len(inputs) == batch_size
    # Mix in images produced from the GenFunc
    # Choose a random number of generated images to mix in, and mix them in randomly
    NGenMB = np.random.randint(0, len(inputs))
    indices = np.arange(len(inputs))
    np.random.shuffle(indices)

    G_inseed =  np.random.rand(NGenMB, 128, 1, 1).astype('float32')
    inputs[0:NGenMB] = GenFunc(G_inseed)
    targets[0:NGenMB] = np.zeros((NGenMB, )).astype('int32')

#    inputs[NGenMB:] += next(GenFunc(n_examples=(len(inputs)-NGenMB)))


#    IDX = inputs[NGenMB:] < 0.4
#    inputs[NGenMB:][IDX] = 0.0
#
#    IDX = inputs[NGenMB:] > 1
#    inputs[NGenMB:][IDX] = 1.0

    return inputs[indices], targets[indices]


def iterate_minibatches(inputs, targets, batchsize, shuffle=False):
    assert len(inputs) == len(targets)
    if shuffle:
        indices = np.arange(len(inputs))
        np.random.shuffle(indices)
    for start_idx in range(0, len(inputs) - batchsize + 1, batchsize):
        if shuffle:
            excerpt = indices[start_idx:start_idx + batchsize]
        else:
            excerpt = slice(start_idx, start_idx + batchsize)

    yield (inputs[excerpt], targets[excerpt])


def run(X_train, y_train, X_test, y_test, X_val, y_val, num_epochs, train_fn_classifier, train_fn_generator, val_fn, genfunc):
    print("Starting training...")
    # We iterate over epochs:
    for epoch in range(num_epochs):
        # In each epoch, we do a full pass over the training data:
        train_err = 0
        train_batches = 0
        start_time = time.time()


        for batch in iterate_minibatches(X_train, y_train, batch_size, shuffle=True):
            inputs, targets = mixin(batch, genfunc)
            train_err += train_fn_classifier(inputs, targets)
            train_batches += 1

        # And a full pass over the validation data:
        val_err = 0
        val_acc = 0
        val_batches = 0
        for batch in iterate_minibatches(X_val, y_val, batch_size, shuffle=True):
            inputs, targets = mixin(batch, genfunc)
            err, acc = val_fn(inputs, targets)
            val_err += err
            val_acc += acc
            val_batches += 1

        # Then we print the results for this epoch:
        print("Epoch {} of {} took {:.3f}s".format(
                epoch + 1, num_epochs, time.time() - start_time))
        print("  training loss:\t\t{:.6f}".format(train_err / train_batches))
        print("  validation loss:\t\t{:.6f}".format(val_err / val_batches))
        print("  validation accuracy:\t\t{:.2f} %".format(
                val_acc / val_batches * 100))

    # After training, we compute and print the test error:
    test_err = 0
    test_acc = 0
    test_batches = 0
    for batch in iterate_minibatches(X_test, y_test, batch_size, shuffle=True):
        inputs, targets = mixin(batch, genfunc)
        err, acc = val_fn(inputs, targets)
        test_err += err
        test_acc += acc
        test_batches += 1
    print("Final results:")
    print("  test loss:\t\t\t{:.6f}".format(test_err / test_batches))
    print("  test accuracy:\t\t{:.2f} %".format(
            test_acc / test_batches * 100))


def main(num_epochs=500):

    # Prepare Theano variables for inputs and targets
    C_in = T.tensor4('inputs')
    C_target = T.ivector('targets')

    G_in = T.tensor4('random')
    G_out = T.tensor4('genout')


    # Load the data
    (X_train, y_train, X_test,y_test, X_val, y_val) = load_dataset()

    # Classifier
    C_network = classifier(C_in)
    C_out = lasagne.layers.get_output(C_network)
    C_params = lasagne.layers.get_all_params(C_network, trainable=True)


    # Define the synthesiser function (that tries to create 'real' images)
    G_network = synthesiser(G_in)
    G_out = lasagne.layers.get_output(G_network)
    G_params = lasagne.layers.get_all_params(G_network, trainable=True)

    # This is a runner, which is used to wire up the output of G_in, with C_out
    # Runner
    R_network = classifier(G_out)
    R_out = lasagne.layers.get_output(R_network)
    R_params = lasagne.layers.get_all_params(R_network, trainable=True)


    # Define the objective, updates, and training functions
    C_obj = lasagne.objectives.categorical_crossentropy(C_out, C_target).mean()
    C_updates = lasagne.updates.nesterov_momentum(
            C_obj, C_params, learning_rate=0.01, momentum=0.9)
    C_train = theano.function([C_in, C_target], C_obj, updates=C_updates)

    G_obj = -lasagne.objectives.categorical_crossentropy(R_out, C_target).mean()
    G_updates = lasagne.updates.nesterov_momentum(
            G_obj, G_params, learning_rate=0.01, momentum=0.9)
    G_train = theano.function([G_in, C_target], G_obj, updates=G_updates)



    # Create the theano functions
    classify = theano.function([C_in], C_out)
    generate = theano.function([G_in], G_out)

    # This section shouldn't change
    test_prediction = lasagne.layers.get_output(C_network, deterministic=True)
    test_loss = lasagne.objectives.categorical_crossentropy(test_prediction,
                                                            C_target)
    test_loss = test_loss.mean()
    test_acc = T.mean(T.eq(T.argmax(test_prediction, axis=1), C_target),
                      dtype=theano.config.floatX)

    # Compile the training and validation functions
    val_fn = theano.function([C_in, C_target], [test_loss, test_acc])

    # Run
    run(X_train, y_train,
        X_test, y_test,
        X_val, y_val,
        num_epochs,
        C_train, G_train, val_fn, generate)

if __name__=='__main__':
    main()





