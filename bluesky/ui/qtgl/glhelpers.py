"""
BlueSky-QtGL tools       : Tools and objects that are used in the BlueSky-QtGL implementation

Methods:
    load_texture(fname)  : GL-texture load function. Returns id of new texture
    BlueSkyProgram()     : Constructor of a BlueSky shader program object: the main shader object in BlueSky-QtGL


Internal methods and classes:
    create_font_array()
    create_attrib_from_glbuf()
    create_attrib_from_nparray()


Created by    : Joost Ellerbroek
Date          : April 2015

Modification  :
By            :
Date          :
------------------------------------------------------------------
"""
try:
    from PyQt5.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics
except ImportError:
    from PyQt4.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics
import OpenGL.GL as gl
import numpy as np
from ctypes import c_void_p, pointer, sizeof


def load_texture(fname):
    img = QImage(fname)
    ptr = c_void_p(int(img.constBits()))

    tex_id = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex_id)
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA8, img.width(), img.height(), 0, gl.GL_BGRA, gl.GL_UNSIGNED_BYTE, ptr)
    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    return tex_id


def create_empty_buffer(size, target=gl.GL_ARRAY_BUFFER, usage=gl.GL_STATIC_DRAW):
    buf_id = gl.glGenBuffers(1)
    gl.glBindBuffer(target, buf_id)
    gl.glBufferData(target, size, None, usage)
    return buf_id


def update_buffer(buf_id, data, target=gl.GL_ARRAY_BUFFER):
    gl.glBindBuffer(target, buf_id)
    gl.glBufferSubData(target, 0, data.nbytes, data)


class UniformBuffer(object):
    max_binding = 1

    def __init__(self, data):
        self.data = data
        self.nbytes = sizeof(data)
        self.ubo = gl.glGenBuffers(1)
        self.binding = self.max_binding
        gl.glBindBuffer(gl.GL_UNIFORM_BUFFER, self.ubo)
        gl.glBufferData(gl.GL_UNIFORM_BUFFER, self.nbytes, pointer(self.data), gl.GL_STREAM_DRAW)
        gl.glBindBufferBase(gl.GL_UNIFORM_BUFFER, self.binding, self.ubo)
        UniformBuffer.max_binding += 1

    def update(self, offset=0, size=None):
        if size is None:
            size = self.nbytes
        gl.glBindBuffer(gl.GL_UNIFORM_BUFFER, self.ubo)
        gl.glBufferSubData(gl.GL_UNIFORM_BUFFER, offset, size, pointer(self.data))


class BlueSkyProgram():
    # Static variables
    initialized = False

    def __init__(self, vertex_shader, fragment_shader, geom_shader=None):
        self.shaders = []
        self.compile_shader(vertex_shader, gl.GL_VERTEX_SHADER)
        self.compile_shader(fragment_shader, gl.GL_FRAGMENT_SHADER)
        if geom_shader is not None:
            self.compile_shader(geom_shader, gl.GL_GEOMETRY_SHADER)
        self.link()

    def compile_shader(self, fname, type):
        """Compile a vertex shader from source."""
        source = open(fname, 'r').read()
        shader = gl.glCreateShader(type)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        # check compilation error
        result = gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS)
        if not(result):
            raise RuntimeError(gl.glGetShaderInfoLog(shader))
            gl.glDeleteShader(shader)
            return

        self.shaders.append(shader)

    def link(self):
        """Create a shader program with from compiled shaders."""
        self.program = gl.glCreateProgram()
        for i in range(0, len(self.shaders)):
            gl.glAttachShader(self.program, self.shaders[i])

        gl.glLinkProgram(self.program)
        # check linking error
        result = gl.glGetProgramiv(self.program, gl.GL_LINK_STATUS)
        if not(result):
            raise RuntimeError(gl.glGetProgramInfoLog(self.program))
            gl.glDeleteProgram(self.program)
            for i in range(0, len(self.shaders)):
                gl.glDeleteShader(self.shaders[i])

        # Clean up
        for i in range(0, len(self.shaders)):
            gl.glDetachShader(self.program, self.shaders[i])
            gl.glDeleteShader(self.shaders[i])

    def use(self):
        gl.glUseProgram(self.program)

    def bind_uniform_buffer(self, ubo_name, ubo):
        idx = gl.glGetUniformBlockIndex(self.program, ubo_name)
        gl.glUniformBlockBinding(self.program, idx, ubo.binding)


class RenderObject(object):
    # Attribute locations
    attrib_vertex, attrib_texcoords, attrib_lat, attrib_lon, attrib_orientation, attrib_color, attrib_texdepth = range(7)
    bound_vao = -1

    def __init__(self, primitive_type=None, first_vertex=0, vertex_count=0, n_instances=0):
        self.vao_id               = gl.glGenVertexArrays(1)
        self.enabled_attributes   = dict()
        self.primitive_type       = primitive_type
        self.first_vertex         = first_vertex
        self.vertex_count         = vertex_count
        self.n_instances          = n_instances
        self.max_instance_divisor = 0

    def set_vertex_count(self, count):
        self.vertex_count = count

    def set_first_vertex(self, vertex):
        self.first_vertex = vertex

    def bind_attrib(self, attrib_id, size, data, storagetype=gl.GL_STATIC_DRAW, instance_divisor=0, datatype=gl.GL_FLOAT, stride=0, offset=None):
        if RenderObject.bound_vao is not self.vao_id:
            gl.glBindVertexArray(self.vao_id)
            RenderObject.bound_vao = self.vao_id

        # Keep track of max instance divisor
        self.max_instance_divisor = max(instance_divisor, self.max_instance_divisor)

        # If the input is an array create a new GL buffer, otherwise assume the buffer already exists and a buffer ID is passed
        if type(data) is np.ndarray:
            # Get an index to one new buffer in GPU mem, bind it, and copy the array data to it
            buf_id = gl.glGenBuffers(1)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buf_id)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, data.nbytes, data, storagetype)
        else:
            # Assume that a GLuint is passed which means that the buffer is already in GPU memory
            buf_id = data
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buf_id)

        # Assign this buffer to one of the attributes in the shader
        gl.glEnableVertexAttribArray(attrib_id)
        gl.glVertexAttribPointer(attrib_id, size, datatype, False, stride, offset)
        # For instanced data, indicate per how many instances we move a step in the buffer (1=per instance)
        if instance_divisor > 0:
            gl.glVertexAttribDivisor(attrib_id, instance_divisor)
        # Clean up
        gl.glDisableVertexAttribArray(attrib_id)

        self.enabled_attributes[attrib_id] = [size, buf_id, instance_divisor, datatype]

        return buf_id

    def bind(self):
        if RenderObject.bound_vao != self.vao_id:
            gl.glBindVertexArray(self.vao_id)
            RenderObject.bound_vao = self.vao_id
            for attrib in self.enabled_attributes:
                gl.glEnableVertexAttribArray(attrib)

    def draw(self, primitive_type=None, first_vertex=None, vertex_count=None, n_instances=None):
        if primitive_type is None:
            primitive_type = self.primitive_type

        if first_vertex is None:
            first_vertex = self.first_vertex

        if vertex_count is None:
            vertex_count = self.vertex_count

        if n_instances is None:
            n_instances = self.n_instances

        if vertex_count == 0:
            return

        self.bind()

        if n_instances > 0:
            gl.glDrawArraysInstanced(primitive_type, first_vertex, vertex_count, n_instances * self.max_instance_divisor)
        else:
            gl.glDrawArrays(primitive_type, first_vertex, vertex_count)

    @staticmethod
    def unbind_all():
        gl.glBindVertexArray(0)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        RenderObject.bound_vao = -1

    @staticmethod
    def copy(original):
        """ Copy a renderobject from one context to the other.
        """
        new = RenderObject(original.primitive_type, original.first_vertex, original.vertex_count, original.n_instances)

        # Bind the same attributes for the new renderobject
        # [size, buf_id, instance_divisor, datatype]
        for attrib, params in original.enabled_attributes.iteritems():
            new.bind_attrib(attrib, params[0], params[1], instance_divisor=params[2], datatype=params[3])

        # Copy possible object attributes that were added to the renderobject
        for attr, val in original.__dict__.iteritems():
            if attr not in new.__dict__:
                setattr(new, attr, val)

        return new


class Font(object):
    # Attribute locations
    attrib_vertex, attrib_texcoords, attrib_lat, attrib_lon, attrib_orientation, attrib_color, attrib_texdepth = range(7)

    def __init__(self, tex_id=0, char_ar=1.0):
        self.tex_id         = tex_id
        self.loc_char_size  = 0
        self.loc_block_size = 0
        self.char_ar        = char_ar

    def copy(self):
        return Font(self.tex_id, self.char_ar)

    def init_shader(self, program):
        self.loc_char_size = gl.glGetUniformLocation(program.program, 'char_size')
        self.loc_block_size = gl.glGetUniformLocation(program.program, 'block_size')

    def use(self):
        gl.glActiveTexture(gl.GL_TEXTURE0+0)
        gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, self.tex_id)

    def set_char_size(self, char_size):
        gl.glUniform2f(self.loc_char_size, char_size, char_size*self.char_ar)

    def set_block_size(self, block_size):
        gl.glUniform2i(self.loc_block_size, block_size[0], block_size[1])

    def create_font_array(self, char_height=62, pixel_margin=1, font_family='Courier', font_weight=50):
        # Load font and get the dimensions of one character (assuming monospaced font)
        f = QFont(font_family)
        f.setPixelSize(char_height)
        f.setWeight(font_weight)
        fm = QFontMetrics(f, QImage())

        char_width = char_height = 0
        char_y = 999

        for i in range(32, 127):
            bb = fm.boundingRect(chr(i))
            char_width = max(char_width, bb.width())
            char_height = max(char_height, bb.height())
            char_y = min(char_y, bb.y())

        imgsize = (char_width + 2 * pixel_margin, char_height + 2 * pixel_margin)
        self.char_ar = float(imgsize[1]) / imgsize[0]

        # init the image and the painter that will draw the characters to each image
        img = QImage(imgsize[0], imgsize[1], QImage.Format_ARGB32)
        ptr = c_void_p(int(img.constBits()))
        painter = QPainter(img)
        painter.setFont(f)
        painter.setPen(QColor(255, 255, 255, 255))

        # Set-up the texture array
        self.tex_id = gl.glGenTextures(1)
        gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, self.tex_id)
        gl.glTexImage3D(gl.GL_TEXTURE_2D_ARRAY, 0, gl.GL_RGBA8, imgsize[0], imgsize[1], 127 - 32, 0, gl.GL_BGRA, gl.GL_UNSIGNED_BYTE, None)
        gl.glTexParameteri(gl.GL_TEXTURE_2D_ARRAY, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D_ARRAY, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameterf(gl.GL_TEXTURE_2D_ARRAY, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
        gl.glTexParameterf(gl.GL_TEXTURE_2D_ARRAY, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
        # We're using the ASCII range 32-126; space, uppercase, lower case, numbers, brackets, punctuation marks
        for i in range(32, 127):
            img.fill(0)
            painter.drawText(pixel_margin, pixel_margin - char_y, chr(i))
            gl.glTexSubImage3D(gl.GL_TEXTURE_2D_ARRAY, 0, 0, 0, i - 32, imgsize[0], imgsize[1], 1, gl.GL_BGRA, gl.GL_UNSIGNED_BYTE, ptr)

        # We're done, close the painter, and return the texture ID, char width and char height
        painter.end()

    @staticmethod
    def char(x, y, w, h, c=32):
        # Two triangles per character
        vertices  = [(x, y + h), (x, y), (x + w, y + h), (x + w, y + h), (x, y), (x + w, y)]
        texcoords = [(0, 0, c), (0, 1, c), (1, 0, c), (1, 0, c), (0, 1, c), (1, 1, c)]
        return vertices, texcoords

    def prepare_text_string(self, text_string, char_size=16.0, text_color=(0.0, 1.0, 0.0), vertex_offset=(0.0, 0.0)):
        ret = RenderObject(gl.GL_TRIANGLES, vertex_count=6 * len(text_string))

        vertices, texcoords = [], []
        w, h = char_size, char_size * self.char_ar
        x, y = vertex_offset
        for i in range(len(text_string)):
            v, t = self.char(x + i * w, y, w, h, ord(text_string[i]))
            vertices  += v
            texcoords += t

        ret.bind_attrib(self.attrib_vertex, 2, np.array(vertices, dtype=np.float32))
        ret.bind_attrib(self.attrib_texcoords, 3, np.array(texcoords, dtype=np.float32))
        ret.bind_attrib(self.attrib_color, 3, np.array(text_color, dtype=np.float32), instance_divisor=1)

        ret.char_size  = char_size
        ret.block_size = (len(text_string), 1)
        return ret

    def prepare_text_instanced(self, text_array, textblock_size, origin_lat=None, origin_lon=None, text_color=None, char_size=16.0, vertex_offset=(0.0, 0.0)):
        ret       = RenderObject(gl.GL_TRIANGLES, vertex_count=6)
        w, h      = char_size, char_size * self.char_ar
        x, y      = vertex_offset
        v, t      = self.char(x, y, w, h)
        vertices  = v
        texcoords = t
        ret.bind_attrib(self.attrib_vertex, 2, np.array(vertices, dtype=np.float32))
        ret.bind_attrib(self.attrib_texcoords, 3, np.array(texcoords, dtype=np.float32))

        ret.bind_attrib(self.attrib_texdepth, 1, text_array, instance_divisor=1, datatype=gl.GL_UNSIGNED_BYTE)
        divisor = textblock_size[0] * textblock_size[1]
        if origin_lat is not None:
            ret.bind_attrib(self.attrib_lat, 1, origin_lat, instance_divisor=divisor)
        if origin_lon is not None:
            ret.bind_attrib(self.attrib_lon, 1, origin_lon, instance_divisor=divisor)

        if text_color is not None:
            ret.bind_attrib(self.attrib_color, 3, text_color, instance_divisor=divisor)

        ret.block_size = textblock_size
        ret.char_size = char_size

        return ret
