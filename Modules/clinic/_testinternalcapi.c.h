/*[clinic input]
preserve
[clinic start generated code]*/

#if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)
#  include "pycore_gc.h"          // PyGC_Head
#  include "pycore_runtime.h"     // _Py_ID()
#endif
#include "pycore_modsupport.h"    // _PyArg_UnpackKeywords()

PyDoc_STRVAR(_testinternalcapi_compiler_cleandoc__doc__,
"compiler_cleandoc($module, /, doc)\n"
"--\n"
"\n"
"C implementation of inspect.cleandoc().");

#define _TESTINTERNALCAPI_COMPILER_CLEANDOC_METHODDEF    \
    {"compiler_cleandoc", _PyCFunction_CAST(_testinternalcapi_compiler_cleandoc), METH_FASTCALL|METH_KEYWORDS, _testinternalcapi_compiler_cleandoc__doc__},

static PyObject *
_testinternalcapi_compiler_cleandoc_impl(PyObject *module, PyObject *doc);

static PyObject *
_testinternalcapi_compiler_cleandoc(PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *return_value = NULL;
    #if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)

    #define NUM_KEYWORDS 1
    static struct {
        PyGC_Head _this_is_not_used;
        PyObject_VAR_HEAD
        PyObject *ob_item[NUM_KEYWORDS];
    } _kwtuple = {
        .ob_base = PyVarObject_HEAD_INIT(&PyTuple_Type, NUM_KEYWORDS)
        .ob_item = { &_Py_ID(doc), },
    };
    #undef NUM_KEYWORDS
    #define KWTUPLE (&_kwtuple.ob_base.ob_base)

    #else  // !Py_BUILD_CORE
    #  define KWTUPLE NULL
    #endif  // !Py_BUILD_CORE

    static const char * const _keywords[] = {"doc", NULL};
    static _PyArg_Parser _parser = {
        .keywords = _keywords,
        .fname = "compiler_cleandoc",
        .kwtuple = KWTUPLE,
    };
    #undef KWTUPLE
    PyObject *argsbuf[1];
    PyObject *doc;

    args = _PyArg_UnpackKeywords(args, nargs, NULL, kwnames, &_parser, 1, 1, 0, argsbuf);
    if (!args) {
        goto exit;
    }
    if (!PyUnicode_Check(args[0])) {
        _PyArg_BadArgument("compiler_cleandoc", "argument 'doc'", "str", args[0]);
        goto exit;
    }
    doc = args[0];
    return_value = _testinternalcapi_compiler_cleandoc_impl(module, doc);

exit:
    return return_value;
}

PyDoc_STRVAR(_testinternalcapi_compiler_codegen__doc__,
"compiler_codegen($module, /, ast, filename, optimize, compile_mode=0)\n"
"--\n"
"\n"
"Apply compiler code generation to an AST.");

#define _TESTINTERNALCAPI_COMPILER_CODEGEN_METHODDEF    \
    {"compiler_codegen", _PyCFunction_CAST(_testinternalcapi_compiler_codegen), METH_FASTCALL|METH_KEYWORDS, _testinternalcapi_compiler_codegen__doc__},

static PyObject *
_testinternalcapi_compiler_codegen_impl(PyObject *module, PyObject *ast,
                                        PyObject *filename, int optimize,
                                        int compile_mode);

static PyObject *
_testinternalcapi_compiler_codegen(PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *return_value = NULL;
    #if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)

    #define NUM_KEYWORDS 4
    static struct {
        PyGC_Head _this_is_not_used;
        PyObject_VAR_HEAD
        PyObject *ob_item[NUM_KEYWORDS];
    } _kwtuple = {
        .ob_base = PyVarObject_HEAD_INIT(&PyTuple_Type, NUM_KEYWORDS)
        .ob_item = { &_Py_ID(ast), &_Py_ID(filename), &_Py_ID(optimize), &_Py_ID(compile_mode), },
    };
    #undef NUM_KEYWORDS
    #define KWTUPLE (&_kwtuple.ob_base.ob_base)

    #else  // !Py_BUILD_CORE
    #  define KWTUPLE NULL
    #endif  // !Py_BUILD_CORE

    static const char * const _keywords[] = {"ast", "filename", "optimize", "compile_mode", NULL};
    static _PyArg_Parser _parser = {
        .keywords = _keywords,
        .fname = "compiler_codegen",
        .kwtuple = KWTUPLE,
    };
    #undef KWTUPLE
    PyObject *argsbuf[4];
    Py_ssize_t noptargs = nargs + (kwnames ? PyTuple_GET_SIZE(kwnames) : 0) - 3;
    PyObject *ast;
    PyObject *filename;
    int optimize;
    int compile_mode = 0;

    args = _PyArg_UnpackKeywords(args, nargs, NULL, kwnames, &_parser, 3, 4, 0, argsbuf);
    if (!args) {
        goto exit;
    }
    ast = args[0];
    filename = args[1];
    optimize = PyLong_AsInt(args[2]);
    if (optimize == -1 && PyErr_Occurred()) {
        goto exit;
    }
    if (!noptargs) {
        goto skip_optional_pos;
    }
    compile_mode = PyLong_AsInt(args[3]);
    if (compile_mode == -1 && PyErr_Occurred()) {
        goto exit;
    }
skip_optional_pos:
    return_value = _testinternalcapi_compiler_codegen_impl(module, ast, filename, optimize, compile_mode);

exit:
    return return_value;
}

PyDoc_STRVAR(_testinternalcapi_optimize_cfg__doc__,
"optimize_cfg($module, /, instructions, consts, nlocals)\n"
"--\n"
"\n"
"Apply compiler optimizations to an instruction list.");

#define _TESTINTERNALCAPI_OPTIMIZE_CFG_METHODDEF    \
    {"optimize_cfg", _PyCFunction_CAST(_testinternalcapi_optimize_cfg), METH_FASTCALL|METH_KEYWORDS, _testinternalcapi_optimize_cfg__doc__},

static PyObject *
_testinternalcapi_optimize_cfg_impl(PyObject *module, PyObject *instructions,
                                    PyObject *consts, int nlocals);

static PyObject *
_testinternalcapi_optimize_cfg(PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *return_value = NULL;
    #if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)

    #define NUM_KEYWORDS 3
    static struct {
        PyGC_Head _this_is_not_used;
        PyObject_VAR_HEAD
        PyObject *ob_item[NUM_KEYWORDS];
    } _kwtuple = {
        .ob_base = PyVarObject_HEAD_INIT(&PyTuple_Type, NUM_KEYWORDS)
        .ob_item = { &_Py_ID(instructions), &_Py_ID(consts), &_Py_ID(nlocals), },
    };
    #undef NUM_KEYWORDS
    #define KWTUPLE (&_kwtuple.ob_base.ob_base)

    #else  // !Py_BUILD_CORE
    #  define KWTUPLE NULL
    #endif  // !Py_BUILD_CORE

    static const char * const _keywords[] = {"instructions", "consts", "nlocals", NULL};
    static _PyArg_Parser _parser = {
        .keywords = _keywords,
        .fname = "optimize_cfg",
        .kwtuple = KWTUPLE,
    };
    #undef KWTUPLE
    PyObject *argsbuf[3];
    PyObject *instructions;
    PyObject *consts;
    int nlocals;

    args = _PyArg_UnpackKeywords(args, nargs, NULL, kwnames, &_parser, 3, 3, 0, argsbuf);
    if (!args) {
        goto exit;
    }
    instructions = args[0];
    consts = args[1];
    nlocals = PyLong_AsInt(args[2]);
    if (nlocals == -1 && PyErr_Occurred()) {
        goto exit;
    }
    return_value = _testinternalcapi_optimize_cfg_impl(module, instructions, consts, nlocals);

exit:
    return return_value;
}

PyDoc_STRVAR(_testinternalcapi_assemble_code_object__doc__,
"assemble_code_object($module, /, filename, instructions, metadata)\n"
"--\n"
"\n"
"Create a code object for the given instructions.");

#define _TESTINTERNALCAPI_ASSEMBLE_CODE_OBJECT_METHODDEF    \
    {"assemble_code_object", _PyCFunction_CAST(_testinternalcapi_assemble_code_object), METH_FASTCALL|METH_KEYWORDS, _testinternalcapi_assemble_code_object__doc__},

static PyObject *
_testinternalcapi_assemble_code_object_impl(PyObject *module,
                                            PyObject *filename,
                                            PyObject *instructions,
                                            PyObject *metadata);

static PyObject *
_testinternalcapi_assemble_code_object(PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *return_value = NULL;
    #if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)

    #define NUM_KEYWORDS 3
    static struct {
        PyGC_Head _this_is_not_used;
        PyObject_VAR_HEAD
        PyObject *ob_item[NUM_KEYWORDS];
    } _kwtuple = {
        .ob_base = PyVarObject_HEAD_INIT(&PyTuple_Type, NUM_KEYWORDS)
        .ob_item = { &_Py_ID(filename), &_Py_ID(instructions), &_Py_ID(metadata), },
    };
    #undef NUM_KEYWORDS
    #define KWTUPLE (&_kwtuple.ob_base.ob_base)

    #else  // !Py_BUILD_CORE
    #  define KWTUPLE NULL
    #endif  // !Py_BUILD_CORE

    static const char * const _keywords[] = {"filename", "instructions", "metadata", NULL};
    static _PyArg_Parser _parser = {
        .keywords = _keywords,
        .fname = "assemble_code_object",
        .kwtuple = KWTUPLE,
    };
    #undef KWTUPLE
    PyObject *argsbuf[3];
    PyObject *filename;
    PyObject *instructions;
    PyObject *metadata;

    args = _PyArg_UnpackKeywords(args, nargs, NULL, kwnames, &_parser, 3, 3, 0, argsbuf);
    if (!args) {
        goto exit;
    }
    filename = args[0];
    instructions = args[1];
    metadata = args[2];
    return_value = _testinternalcapi_assemble_code_object_impl(module, filename, instructions, metadata);

exit:
    return return_value;
}

PyDoc_STRVAR(_testinternalcapi_write_unraisable_exc__doc__,
"write_unraisable_exc($module, exception, err_msg, obj, /)\n"
"--\n"
"\n");

#define _TESTINTERNALCAPI_WRITE_UNRAISABLE_EXC_METHODDEF    \
    {"write_unraisable_exc", _PyCFunction_CAST(_testinternalcapi_write_unraisable_exc), METH_FASTCALL, _testinternalcapi_write_unraisable_exc__doc__},

static PyObject *
_testinternalcapi_write_unraisable_exc_impl(PyObject *module, PyObject *exc,
                                            PyObject *err_msg, PyObject *obj);

static PyObject *
_testinternalcapi_write_unraisable_exc(PyObject *module, PyObject *const *args, Py_ssize_t nargs)
{
    PyObject *return_value = NULL;
    PyObject *exc;
    PyObject *err_msg;
    PyObject *obj;

    if (!_PyArg_CheckPositional("write_unraisable_exc", nargs, 3, 3)) {
        goto exit;
    }
    exc = args[0];
    err_msg = args[1];
    obj = args[2];
    return_value = _testinternalcapi_write_unraisable_exc_impl(module, exc, err_msg, obj);

exit:
    return return_value;
}

PyDoc_STRVAR(_testinternalcapi_test_long_numbits__doc__,
"test_long_numbits($module, /)\n"
"--\n"
"\n");

#define _TESTINTERNALCAPI_TEST_LONG_NUMBITS_METHODDEF    \
    {"test_long_numbits", (PyCFunction)_testinternalcapi_test_long_numbits, METH_NOARGS, _testinternalcapi_test_long_numbits__doc__},

static PyObject *
_testinternalcapi_test_long_numbits_impl(PyObject *module);

static PyObject *
_testinternalcapi_test_long_numbits(PyObject *module, PyObject *Py_UNUSED(ignored))
{
    return _testinternalcapi_test_long_numbits_impl(module);
}
/*[clinic end generated code: output=3425f97821fc7462 input=a9049054013a1b77]*/
