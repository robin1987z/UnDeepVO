import tensorflow as tf
from keras.engine import Layer
from keras.layers import Conv2D, BatchNormalization, Activation, Conv2DTranspose, Input, Lambda, concatenate
from keras import backend as K
from keras.models import Model
import keras
from tensorflow.contrib.framework import add_arg_scope


@add_arg_scope
def unpool_2d(pool, ind, stride=None, scope='unpool_2d'):
    if stride is None:
        stride = [1, 2, 2, 1]

    with tf.variable_scope(scope):
        input_shape = tf.shape(pool)
        output_shape = [input_shape[0], input_shape[1] * stride[1], input_shape[2] * stride[2], input_shape[3]]

        flat_input_size = tf.reduce_prod(input_shape)

        flat_output_shape = [output_shape[0], output_shape[1] * output_shape[2] * output_shape[3]]

        pool_ = tf.reshape(pool, [flat_input_size])
        batch_range = tf.reshape(tf.range(tf.cast(output_shape[0], tf.int64), dtype=ind.dtype),
                                 shape=[input_shape[0], 1, 1, 1])

        b = tf.ones_like(ind) * batch_range
        b1 = tf.reshape(b, [flat_input_size, 1])
        ind_ = tf.reshape(ind, [flat_input_size, 1])
        ind_ = tf.concat([b1, ind_], 1)

        ret = tf.scatter_nd(ind_, pool_, shape=tf.cast(flat_output_shape, tf.int64))
        ret = tf.reshape(ret, output_shape)

        set_input_shape = pool.get_shape()
        set_output_shape = [set_input_shape[0], set_input_shape[1] * stride[1], set_input_shape[2] * stride[2],
                            set_input_shape[3]]
        ret.set_shape(set_output_shape)
        return ret


class MaxPooling2DArgMax(Layer):
    def __init__(self, pool_size=(1, 2, 2, 1), strides=(1, 2, 2, 1), padding='SAME', **kwargs):
        self.pool_size = pool_size
        self.strides = strides
        self.padding = padding
        super(MaxPooling2DArgMax, self).__init__(**kwargs)

    def build(self, input_shape):
        super(MaxPooling2DArgMax, self).build(input_shape)

    def call(self, inputs, **kwargs):
        tensor_list = tf.nn.max_pool_with_argmax(inputs, self.pool_size, strides=self.strides, padding=self.padding)
        return [tensor_list[0], tensor_list[1]]

    def compute_output_shape(self, input_shape):
        return [(input_shape[0], input_shape[1] / 2, input_shape[2] / 2, input_shape[3]),
                (input_shape[0], input_shape[1] / 2, input_shape[2] / 2, input_shape[3])]


class MaxUnPooling2DArgMax(Layer):
    def __init__(self, stride=(1, 2, 2, 1), **kwargs):
        self.stride = stride
        super(MaxUnPooling2DArgMax, self).__init__(**kwargs)

    def build(self, input_shape):
        super(MaxUnPooling2DArgMax, self).build(input_shape)

    def call(self, inputs, **kwargs):
        indices = kwargs.get('indices')
        return unpool_2d(inputs, indices)

    def compute_output_shape(self, input_shape):
        return input_shape[0], input_shape[1] * self.stride[1], input_shape[2] * self.stride[2], input_shape[3]


def conv2d_relu_batchnorm(channels, kernel_size, inputs):
    return Activation(activation='relu')(BatchNormalization()(Conv2D(channels, kernel_size=kernel_size, padding='SAME')(inputs)))


def deconv2d_relu_batchnorm(channels, kernel_size, inputs):
    return Activation(activation='relu')(BatchNormalization()(Conv2DTranspose(channels, kernel_size=kernel_size, padding='SAME')(inputs)))


def conv2d_block(channels, kernel_size, inputs):
    conv1 = conv2d_relu_batchnorm(channels, kernel_size, inputs)

    conv2 = conv2d_relu_batchnorm(channels, kernel_size, conv1)

    return MaxPooling2DArgMax()(conv2)


def conv2d_block_2(channels, kernel_size, kernel_size_1, inputs):
    conv1 = conv2d_relu_batchnorm(channels, kernel_size, inputs)

    conv2 = conv2d_relu_batchnorm(channels, kernel_size, conv1)

    conv3 = conv2d_relu_batchnorm(channels, kernel_size, conv2)

    return MaxPooling2DArgMax()(conv3)


def deconv2d_block(channels, kernel_size, pool, indices):

    unpool1 = MaxUnPooling2DArgMax()(pool, indices=indices)

    unconv1 = deconv2d_relu_batchnorm(channels, kernel_size, unpool1)

    return deconv2d_relu_batchnorm(channels, kernel_size, unconv1)


def deconv2d_block_2(channels, kernel_size, kernel_size_1, pool, indices):
    unpool1 = MaxUnPooling2DArgMax()(pool, indices=indices)

    unconv1 = deconv2d_relu_batchnorm(channels, kernel_size, unpool1)

    unconv2 = deconv2d_relu_batchnorm(channels, kernel_size_1, unconv1)

    return deconv2d_relu_batchnorm(channels, kernel_size_1, unconv2)


def get_undeepvo_net(img_rows, img_cols, learning_rate=1e-4):

    if K.image_data_format() == 'channels_first':
        input_shape = (3, img_rows, 2 * img_cols)
    else:
        input_shape = (img_rows, 2 * img_cols, 3)

    inputs = Input(input_shape)

    left_image = Lambda(lambda x: x[..., :img_cols, :])(inputs)

    right_image = Lambda(lambda x: x[..., img_cols:, :])(inputs)

    cat_image = concatenate([left_image, right_image], axis=3)

    conv_block1, indices1 = conv2d_block(32, (7, 7), left_image)

    conv_block2, indices2 = conv2d_block(64, (5, 5), conv_block1)

    conv_block3, indices3 = conv2d_block(128, (3, 3), conv_block2)

    conv_block4, indices4 = conv2d_block(256, (3, 3), conv_block3)

    conv_block5, indices5 = conv2d_block(512, (3, 3), conv_block4)

    conv_block6, indices6 = conv2d_block(512, (3, 3), conv_block5)

    conv_block7, indices7 = conv2d_block(512, (3, 3), conv_block6)

    deconv_block7 = deconv2d_block(512, (3, 3), conv_block7, indices6)

    deconv_block6 = deconv2d_block(512, (3, 3), deconv_block7, indices5)

    deconv_block5 = deconv2d_block(256, (3, 3), deconv_block6, indices4)

    deconv_block4 = deconv2d_block(128, (3, 3), deconv_block5, indices3)

    deconv_block3 = deconv2d_block(64, (3, 3), deconv_block4, indices2)

    deconv_block2 = deconv2d_block(32, (3, 3), deconv_block3, indices1)

    deconv_block1 = deconv2d_relu_batchnorm(16, (3, 3), deconv_block2)

    model = Model(inputs=inputs, outputs=deconv_block1)

    model.compile(loss=keras.losses.categorical_crossentropy,
                  optimizer=keras.optimizers.Adadelta(),
                  metrics=['accuracy'])

    model.summary()

    return model

