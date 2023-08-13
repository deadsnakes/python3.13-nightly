# Argument Clinic
# Copyright 2012-2013 by Larry Hastings.
# Licensed to the PSF under a contributor agreement.

from functools import partial
from test import support, test_tools
from test.support import os_helper
from test.support.os_helper import TESTFN, unlink
from textwrap import dedent
from unittest import TestCase
import contextlib
import inspect
import os.path
import re
import sys
import unittest

test_tools.skip_if_missing('clinic')
with test_tools.imports_under_tool('clinic'):
    import clinic
    from clinic import DSLParser


def _make_clinic(*, filename='clinic_tests'):
    clang = clinic.CLanguage(None)
    c = clinic.Clinic(clang, filename=filename)
    c.block_parser = clinic.BlockParser('', clang)
    return c


def _expect_failure(tc, parser, code, errmsg, *, filename=None, lineno=None):
    """Helper for the parser tests.

    tc: unittest.TestCase; passed self in the wrapper
    parser: the clinic parser used for this test case
    code: a str with input text (clinic code)
    errmsg: the expected error message
    filename: str, optional filename
    lineno: int, optional line number
    """
    code = dedent(code).strip()
    errmsg = re.escape(errmsg)
    with tc.assertRaisesRegex(clinic.ClinicError, errmsg) as cm:
        parser(code)
    if filename is not None:
        tc.assertEqual(cm.exception.filename, filename)
    if lineno is not None:
        tc.assertEqual(cm.exception.lineno, lineno)
    return cm.exception


class ClinicWholeFileTest(TestCase):
    maxDiff = None

    def expect_failure(self, raw, errmsg, *, filename=None, lineno=None):
        _expect_failure(self, self.clinic.parse, raw, errmsg,
                        filename=filename, lineno=lineno)

    def setUp(self):
        self.clinic = _make_clinic(filename="test.c")

    def test_eol(self):
        # regression test:
        # clinic's block parser didn't recognize
        # the "end line" for the block if it
        # didn't end in "\n" (as in, the last)
        # byte of the file was '/'.
        # so it would spit out an end line for you.
        # and since you really already had one,
        # the last line of the block got corrupted.
        raw = "/*[clinic]\nfoo\n[clinic]*/"
        cooked = self.clinic.parse(raw).splitlines()
        end_line = cooked[2].rstrip()
        # this test is redundant, it's just here explicitly to catch
        # the regression test so we don't forget what it looked like
        self.assertNotEqual(end_line, "[clinic]*/[clinic]*/")
        self.assertEqual(end_line, "[clinic]*/")

    def test_mangled_marker_line(self):
        raw = """
            /*[clinic input]
            [clinic start generated code]*/
            /*[clinic end generated code: foo]*/
        """
        err = (
            "Mangled Argument Clinic marker line: "
            "'/*[clinic end generated code: foo]*/'"
        )
        self.expect_failure(raw, err, filename="test.c", lineno=3)

    def test_checksum_mismatch(self):
        raw = """
            /*[clinic input]
            [clinic start generated code]*/
            /*[clinic end generated code: output=0123456789abcdef input=fedcba9876543210]*/
        """
        err = ("Checksum mismatch! "
               "Expected '0123456789abcdef', computed 'da39a3ee5e6b4b0d'")
        self.expect_failure(raw, err, filename="test.c", lineno=3)

    def test_garbage_after_stop_line(self):
        raw = """
            /*[clinic input]
            [clinic start generated code]*/foobarfoobar!
        """
        err = "Garbage after stop line: 'foobarfoobar!'"
        self.expect_failure(raw, err, filename="test.c", lineno=2)

    def test_whitespace_before_stop_line(self):
        raw = """
            /*[clinic input]
             [clinic start generated code]*/
        """
        err = (
            "Whitespace is not allowed before the stop line: "
            "' [clinic start generated code]*/'"
        )
        self.expect_failure(raw, err, filename="test.c", lineno=2)

    def test_parse_with_body_prefix(self):
        clang = clinic.CLanguage(None)
        clang.body_prefix = "//"
        clang.start_line = "//[{dsl_name} start]"
        clang.stop_line = "//[{dsl_name} stop]"
        cl = clinic.Clinic(clang, filename="test.c")
        raw = dedent("""
            //[clinic start]
            //module test
            //[clinic stop]
        """).strip()
        out = cl.parse(raw)
        expected = dedent("""
            //[clinic start]
            //module test
            //
            //[clinic stop]
            /*[clinic end generated code: output=da39a3ee5e6b4b0d input=65fab8adff58cf08]*/
        """).lstrip()  # Note, lstrip() because of the newline
        self.assertEqual(out, expected)

    def test_cpp_monitor_fail_nested_block_comment(self):
        raw = """
            /* start
            /* nested
            */
            */
        """
        err = 'Nested block comment!'
        self.expect_failure(raw, err, filename="test.c", lineno=2)

    def test_cpp_monitor_fail_invalid_format_noarg(self):
        raw = """
            #if
            a()
            #endif
        """
        err = 'Invalid format for #if line: no argument!'
        self.expect_failure(raw, err, filename="test.c", lineno=1)

    def test_cpp_monitor_fail_invalid_format_toomanyargs(self):
        raw = """
            #ifdef A B
            a()
            #endif
        """
        err = 'Invalid format for #ifdef line: should be exactly one argument!'
        self.expect_failure(raw, err, filename="test.c", lineno=1)

    def test_cpp_monitor_fail_no_matching_if(self):
        raw = '#else'
        err = '#else without matching #if / #ifdef / #ifndef!'
        self.expect_failure(raw, err, filename="test.c", lineno=1)

    def test_directive_output_unknown_preset(self):
        raw = """
            /*[clinic input]
            output preset nosuchpreset
            [clinic start generated code]*/
        """
        err = "Unknown preset 'nosuchpreset'"
        self.expect_failure(raw, err)

    def test_directive_output_cant_pop(self):
        raw = """
            /*[clinic input]
            output pop
            [clinic start generated code]*/
        """
        err = "Can't 'output pop', stack is empty"
        self.expect_failure(raw, err)

    def test_directive_output_print(self):
        raw = dedent("""
            /*[clinic input]
            output print 'I told you once.'
            [clinic start generated code]*/
        """)
        out = self.clinic.parse(raw)
        # The generated output will differ for every run, but we can check that
        # it starts with the clinic block, we check that it contains all the
        # expected fields, and we check that it contains the checksum line.
        self.assertTrue(out.startswith(dedent("""
            /*[clinic input]
            output print 'I told you once.'
            [clinic start generated code]*/
        """)))
        fields = {
            "cpp_endif",
            "cpp_if",
            "docstring_definition",
            "docstring_prototype",
            "impl_definition",
            "impl_prototype",
            "methoddef_define",
            "methoddef_ifndef",
            "parser_definition",
            "parser_prototype",
        }
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, out)
        last_line = out.rstrip().split("\n")[-1]
        self.assertTrue(
            last_line.startswith("/*[clinic end generated code: output=")
        )

    def test_directive_wrong_arg_number(self):
        raw = dedent("""
            /*[clinic input]
            preserve foo bar baz eggs spam ham mushrooms
            [clinic start generated code]*/
        """)
        err = "takes 1 positional argument but 8 were given"
        self.expect_failure(raw, err)

    def test_unknown_destination_command(self):
        raw = """
            /*[clinic input]
            destination buffer nosuchcommand
            [clinic start generated code]*/
        """
        err = "unknown destination command 'nosuchcommand'"
        self.expect_failure(raw, err)

    def test_no_access_to_members_in_converter_init(self):
        raw = """
            /*[python input]
            class Custom_converter(CConverter):
                converter = "some_c_function"
                def converter_init(self):
                    self.function.noaccess
            [python start generated code]*/
            /*[clinic input]
            module test
            test.fn
                a: Custom
            [clinic start generated code]*/
        """
        err = (
            "accessing self.function inside converter_init is disallowed!"
        )
        self.expect_failure(raw, err)

    @staticmethod
    @contextlib.contextmanager
    def _clinic_version(new_version):
        """Helper for test_version_*() tests"""
        _saved = clinic.version
        clinic.version = new_version
        try:
            yield
        finally:
            clinic.version = _saved

    def test_version_directive(self):
        dataset = (
            # (clinic version, required version)
            ('3', '2'),          # required version < clinic version
            ('3.1', '3.0'),      # required version < clinic version
            ('1.2b0', '1.2a7'),  # required version < clinic version
            ('5', '5'),          # required version == clinic version
            ('6.1', '6.1'),      # required version == clinic version
            ('1.2b3', '1.2b3'),  # required version == clinic version
        )
        for clinic_version, required_version in dataset:
            with self.subTest(clinic_version=clinic_version,
                              required_version=required_version):
                with self._clinic_version(clinic_version):
                    block = dedent(f"""
                        /*[clinic input]
                        version {required_version}
                        [clinic start generated code]*/
                    """)
                    self.clinic.parse(block)

    def test_version_directive_insufficient_version(self):
        with self._clinic_version('4'):
            err = (
                "Insufficient Clinic version!\n"
                "  Version: 4\n"
                "  Required: 5"
            )
            block = """
                /*[clinic input]
                version 5
                [clinic start generated code]*/
            """
            self.expect_failure(block, err)

    def test_version_directive_illegal_char(self):
        err = "Illegal character 'v' in version string 'v5'"
        block = """
            /*[clinic input]
            version v5
            [clinic start generated code]*/
        """
        self.expect_failure(block, err)

    def test_version_directive_unsupported_string(self):
        err = "Unsupported version string: '.-'"
        block = """
            /*[clinic input]
            version .-
            [clinic start generated code]*/
        """
        self.expect_failure(block, err)

    def test_clone_mismatch(self):
        err = "'kind' of function and cloned function don't match!"
        block = """
            /*[clinic input]
            module m
            @classmethod
            m.f1
                a: object
            [clinic start generated code]*/
            /*[clinic input]
            @staticmethod
            m.f2 = m.f1
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=9)

    def test_badly_formed_return_annotation(self):
        err = "Badly formed annotation for 'm.f': 'Custom'"
        block = """
            /*[python input]
            class Custom_return_converter(CReturnConverter):
                def __init__(self):
                    raise ValueError("abc")
            [python start generated code]*/
            /*[clinic input]
            module m
            m.f -> Custom
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=8)

    def test_module_already_got_one(self):
        err = "Already defined module 'm'!"
        block = """
            /*[clinic input]
            module m
            module m
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=3)

    def test_destination_already_got_one(self):
        err = "Destination already exists: 'test'"
        block = """
            /*[clinic input]
            destination test new buffer
            destination test new buffer
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=3)

    def test_destination_does_not_exist(self):
        err = "Destination does not exist: '/dev/null'"
        block = """
            /*[clinic input]
            output everything /dev/null
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=2)

    def test_class_already_got_one(self):
        err = "Already defined class 'C'!"
        block = """
            /*[clinic input]
            class C "" ""
            class C "" ""
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=3)

    def test_cant_nest_module_inside_class(self):
        err = "Can't nest a module inside a class!"
        block = """
            /*[clinic input]
            class C "" ""
            module C.m
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=3)

    def test_dest_buffer_not_empty_at_eof(self):
        expected_warning = ("Destination buffer 'buffer' not empty at "
                            "end of file, emptying.")
        expected_generated = dedent("""
            /*[clinic input]
            output everything buffer
            fn
                a: object
                /
            [clinic start generated code]*/
            /*[clinic end generated code: output=da39a3ee5e6b4b0d input=1c4668687f5fd002]*/

            /*[clinic input]
            dump buffer
            [clinic start generated code]*/

            PyDoc_VAR(fn__doc__);

            PyDoc_STRVAR(fn__doc__,
            "fn($module, a, /)\\n"
            "--\\n"
            "\\n");

            #define FN_METHODDEF    \\
                {"fn", (PyCFunction)fn, METH_O, fn__doc__},

            static PyObject *
            fn(PyObject *module, PyObject *a)
            /*[clinic end generated code: output=be6798b148ab4e53 input=524ce2e021e4eba6]*/
        """)
        block = dedent("""
            /*[clinic input]
            output everything buffer
            fn
                a: object
                /
            [clinic start generated code]*/
        """)
        with support.captured_stdout() as stdout:
            generated = self.clinic.parse(block)
        self.assertIn(expected_warning, stdout.getvalue())
        self.assertEqual(generated, expected_generated)

    def test_dest_clear(self):
        err = "Can't clear destination 'file': it's not of type 'buffer'"
        block = """
            /*[clinic input]
            destination file clear
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=2)

    def test_directive_set_misuse(self):
        err = "unknown variable 'ets'"
        block = """
            /*[clinic input]
            set ets tse
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=2)

    def test_directive_set_prefix(self):
        block = dedent("""
            /*[clinic input]
            set line_prefix '// '
            output everything suppress
            output docstring_prototype buffer
            fn
                a: object
                /
            [clinic start generated code]*/
            /* We need to dump the buffer.
             * If not, Argument Clinic will emit a warning */
            /*[clinic input]
            dump buffer
            [clinic start generated code]*/
        """)
        generated = self.clinic.parse(block)
        expected_docstring_prototype = "// PyDoc_VAR(fn__doc__);"
        self.assertIn(expected_docstring_prototype, generated)

    def test_directive_set_suffix(self):
        block = dedent("""
            /*[clinic input]
            set line_suffix '  // test'
            output everything suppress
            output docstring_prototype buffer
            fn
                a: object
                /
            [clinic start generated code]*/
            /* We need to dump the buffer.
             * If not, Argument Clinic will emit a warning */
            /*[clinic input]
            dump buffer
            [clinic start generated code]*/
        """)
        generated = self.clinic.parse(block)
        expected_docstring_prototype = "PyDoc_VAR(fn__doc__);  // test"
        self.assertIn(expected_docstring_prototype, generated)

    def test_directive_set_prefix_and_suffix(self):
        block = dedent("""
            /*[clinic input]
            set line_prefix '{block comment start} '
            set line_suffix ' {block comment end}'
            output everything suppress
            output docstring_prototype buffer
            fn
                a: object
                /
            [clinic start generated code]*/
            /* We need to dump the buffer.
             * If not, Argument Clinic will emit a warning */
            /*[clinic input]
            dump buffer
            [clinic start generated code]*/
        """)
        generated = self.clinic.parse(block)
        expected_docstring_prototype = "/* PyDoc_VAR(fn__doc__); */"
        self.assertIn(expected_docstring_prototype, generated)

    def test_directive_printout(self):
        block = dedent("""
            /*[clinic input]
            output everything buffer
            printout test
            [clinic start generated code]*/
        """)
        expected = dedent("""
            /*[clinic input]
            output everything buffer
            printout test
            [clinic start generated code]*/
            test
            /*[clinic end generated code: output=4e1243bd22c66e76 input=898f1a32965d44ca]*/
        """)
        generated = self.clinic.parse(block)
        self.assertEqual(generated, expected)

    def test_directive_preserve_twice(self):
        err = "Can't have 'preserve' twice in one block!"
        block = """
            /*[clinic input]
            preserve
            preserve
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=3)

    def test_directive_preserve_input(self):
        err = "'preserve' only works for blocks that don't produce any output!"
        block = """
            /*[clinic input]
            preserve
            fn
                a: object
                /
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=6)

    def test_directive_preserve_output(self):
        block = dedent("""
            /*[clinic input]
            output everything buffer
            preserve
            [clinic start generated code]*/
            // Preserve this
            /*[clinic end generated code: output=eaa49677ae4c1f7d input=559b5db18fddae6a]*/
            /*[clinic input]
            dump buffer
            [clinic start generated code]*/
            /*[clinic end generated code: output=da39a3ee5e6b4b0d input=524ce2e021e4eba6]*/
        """)
        generated = self.clinic.parse(block)
        self.assertEqual(generated, block)

    def test_directive_output_invalid_command(self):
        err = dedent("""
            Invalid command or destination name 'cmd'. Must be one of:
             - 'preset'
             - 'push'
             - 'pop'
             - 'print'
             - 'everything'
             - 'cpp_if'
             - 'docstring_prototype'
             - 'docstring_definition'
             - 'methoddef_define'
             - 'impl_prototype'
             - 'parser_prototype'
             - 'parser_definition'
             - 'cpp_endif'
             - 'methoddef_ifndef'
             - 'impl_definition'
        """).strip()
        block = """
            /*[clinic input]
            output cmd buffer
            [clinic start generated code]*/
        """
        self.expect_failure(block, err, lineno=2)


class ParseFileUnitTest(TestCase):
    def expect_parsing_failure(
        self, *, filename, expected_error, verify=True, output=None
    ):
        errmsg = re.escape(dedent(expected_error).strip())
        with self.assertRaisesRegex(clinic.ClinicError, errmsg):
            clinic.parse_file(filename)

    def test_parse_file_no_extension(self) -> None:
        self.expect_parsing_failure(
            filename="foo",
            expected_error="Can't extract file type for file 'foo'"
        )

    def test_parse_file_strange_extension(self) -> None:
        filenames_to_errors = {
            "foo.rs": "Can't identify file type for file 'foo.rs'",
            "foo.hs": "Can't identify file type for file 'foo.hs'",
            "foo.js": "Can't identify file type for file 'foo.js'",
        }
        for filename, errmsg in filenames_to_errors.items():
            with self.subTest(filename=filename):
                self.expect_parsing_failure(filename=filename, expected_error=errmsg)


class ClinicGroupPermuterTest(TestCase):
    def _test(self, l, m, r, output):
        computed = clinic.permute_optional_groups(l, m, r)
        self.assertEqual(output, computed)

    def test_range(self):
        self._test([['start']], ['stop'], [['step']],
          (
            ('stop',),
            ('start', 'stop',),
            ('start', 'stop', 'step',),
          ))

    def test_add_window(self):
        self._test([['x', 'y']], ['ch'], [['attr']],
          (
            ('ch',),
            ('ch', 'attr'),
            ('x', 'y', 'ch',),
            ('x', 'y', 'ch', 'attr'),
          ))

    def test_ludicrous(self):
        self._test([['a1', 'a2', 'a3'], ['b1', 'b2']], ['c1'], [['d1', 'd2'], ['e1', 'e2', 'e3']],
          (
          ('c1',),
          ('b1', 'b2', 'c1'),
          ('b1', 'b2', 'c1', 'd1', 'd2'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1', 'd1', 'd2'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1', 'd1', 'd2', 'e1', 'e2', 'e3'),
          ))

    def test_right_only(self):
        self._test([], [], [['a'],['b'],['c']],
          (
          (),
          ('a',),
          ('a', 'b'),
          ('a', 'b', 'c')
          ))

    def test_have_left_options_but_required_is_empty(self):
        def fn():
            clinic.permute_optional_groups(['a'], [], [])
        self.assertRaises(ValueError, fn)


class ClinicLinearFormatTest(TestCase):
    def _test(self, input, output, **kwargs):
        computed = clinic.linear_format(input, **kwargs)
        self.assertEqual(output, computed)

    def test_empty_strings(self):
        self._test('', '')

    def test_solo_newline(self):
        self._test('\n', '\n')

    def test_no_substitution(self):
        self._test("""
          abc
        """, """
          abc
        """)

    def test_empty_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          def
        """, name='')

    def test_single_line_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          GARGLE
          def
        """, name='GARGLE')

    def test_multiline_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          bingle
          bungle

          def
        """, name='bingle\nbungle\n')

class InertParser:
    def __init__(self, clinic):
        pass

    def parse(self, block):
        pass

class CopyParser:
    def __init__(self, clinic):
        pass

    def parse(self, block):
        block.output = block.input


class ClinicBlockParserTest(TestCase):
    def _test(self, input, output):
        language = clinic.CLanguage(None)

        blocks = list(clinic.BlockParser(input, language))
        writer = clinic.BlockPrinter(language)
        for block in blocks:
            writer.print_block(block)
        output = writer.f.getvalue()
        assert output == input, "output != input!\n\noutput " + repr(output) + "\n\n input " + repr(input)

    def round_trip(self, input):
        return self._test(input, input)

    def test_round_trip_1(self):
        self.round_trip("""
            verbatim text here
            lah dee dah
        """)
    def test_round_trip_2(self):
        self.round_trip("""
    verbatim text here
    lah dee dah
/*[inert]
abc
[inert]*/
def
/*[inert checksum: 7b18d017f89f61cf17d47f92749ea6930a3f1deb]*/
xyz
""")

    def _test_clinic(self, input, output):
        language = clinic.CLanguage(None)
        c = clinic.Clinic(language, filename="file")
        c.parsers['inert'] = InertParser(c)
        c.parsers['copy'] = CopyParser(c)
        computed = c.parse(input)
        self.assertEqual(output, computed)

    def test_clinic_1(self):
        self._test_clinic("""
    verbatim text here
    lah dee dah
/*[copy input]
def
[copy start generated code]*/
abc
/*[copy end generated code: output=03cfd743661f0797 input=7b18d017f89f61cf]*/
xyz
""", """
    verbatim text here
    lah dee dah
/*[copy input]
def
[copy start generated code]*/
def
/*[copy end generated code: output=7b18d017f89f61cf input=7b18d017f89f61cf]*/
xyz
""")


class ClinicParserTest(TestCase):

    def parse(self, text):
        c = _make_clinic()
        parser = DSLParser(c)
        block = clinic.Block(text)
        parser.parse(block)
        return block

    def parse_function(self, text, signatures_in_block=2, function_index=1):
        block = self.parse(text)
        s = block.signatures
        self.assertEqual(len(s), signatures_in_block)
        assert isinstance(s[0], clinic.Module)
        assert isinstance(s[function_index], clinic.Function)
        return s[function_index]

    def expect_failure(self, block, err, *, filename=None, lineno=None):
        return _expect_failure(self, self.parse_function, block, err,
                               filename=filename, lineno=lineno)

    def checkDocstring(self, fn, expected):
        self.assertTrue(hasattr(fn, "docstring"))
        self.assertEqual(dedent(expected).strip(),
                         fn.docstring.strip())

    def test_trivial(self):
        parser = DSLParser(_make_clinic())
        block = clinic.Block("""
            module os
            os.access
        """)
        parser.parse(block)
        module, function = block.signatures
        self.assertEqual("access", function.name)
        self.assertEqual("os", module.name)

    def test_ignore_line(self):
        block = self.parse(dedent("""
            #
            module os
            os.access
        """))
        module, function = block.signatures
        self.assertEqual("access", function.name)
        self.assertEqual("os", module.name)

    def test_param(self):
        function = self.parse_function("""
            module os
            os.access
                path: int
        """)
        self.assertEqual("access", function.name)
        self.assertEqual(2, len(function.parameters))
        p = function.parameters['path']
        self.assertEqual('path', p.name)
        self.assertIsInstance(p.converter, clinic.int_converter)

    def test_param_default(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: bool = True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(True, p.default)

    def test_param_with_continuations(self):
        function = self.parse_function(r"""
            module os
            os.access
                follow_symlinks: \
                bool \
                = \
                True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(True, p.default)

    def test_param_default_expr_named_constant(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: int(c_default='MAXSIZE') = sys.maxsize
            """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(sys.maxsize, p.default)
        self.assertEqual("MAXSIZE", p.converter.c_default)

        err = (
            "When you specify a named constant ('sys.maxsize') as your default value, "
            "you MUST specify a valid c_default."
        )
        block = """
            module os
            os.access
                follow_symlinks: int = sys.maxsize
        """
        self.expect_failure(block, err, lineno=2)

    def test_param_with_bizarre_default_fails_correctly(self):
        template = """
            module os
            os.access
                follow_symlinks: int = {default}
        """
        err = "Unsupported expression as default value"
        for bad_default_value in (
            "{1, 2, 3}",
            "3 if bool() else 4",
            "[x for x in range(42)]"
        ):
            with self.subTest(bad_default=bad_default_value):
                block = template.format(default=bad_default_value)
                self.expect_failure(block, err, lineno=2)

    def test_unspecified_not_allowed_as_default_value(self):
        block = """
            module os
            os.access
                follow_symlinks: int(c_default='MAXSIZE') = unspecified
        """
        err = "'unspecified' is not a legal default value!"
        exc = self.expect_failure(block, err, lineno=2)
        self.assertNotIn('Malformed expression given as default value', str(exc))

    def test_malformed_expression_as_default_value(self):
        block = """
            module os
            os.access
                follow_symlinks: int(c_default='MAXSIZE') = 1/0
        """
        err = "Malformed expression given as default value"
        self.expect_failure(block, err, lineno=2)

    def test_param_default_expr_binop(self):
        err = (
            "When you specify an expression ('a + b') as your default value, "
            "you MUST specify a valid c_default."
        )
        block = """
            fn
                follow_symlinks: int = a + b
        """
        self.expect_failure(block, err, lineno=1)

    def test_param_no_docstring(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: bool = True
                something_else: str = ''
        """)
        self.assertEqual(3, len(function.parameters))
        conv = function.parameters['something_else'].converter
        self.assertIsInstance(conv, clinic.str_converter)

    def test_param_default_parameters_out_of_order(self):
        err = (
            "Can't have a parameter without a default ('something_else') "
            "after a parameter with a default!"
        )
        block = """
            module os
            os.access
                follow_symlinks: bool = True
                something_else: str
        """
        self.expect_failure(block, err, lineno=3)

    def disabled_test_converter_arguments(self):
        function = self.parse_function("""
            module os
            os.access
                path: path_t(allow_fd=1)
        """)
        p = function.parameters['path']
        self.assertEqual(1, p.converter.args['allow_fd'])

    def test_function_docstring(self):
        function = self.parse_function("""
            module os
            os.stat as os_stat_fn

               path: str
                   Path to be examined
                   Ensure that multiple lines are indented correctly.

            Perform a stat system call on the given path.

            Ensure that multiple lines are indented correctly.
            Ensure that multiple lines are indented correctly.
        """)
        self.checkDocstring(function, """
            stat($module, /, path)
            --

            Perform a stat system call on the given path.

              path
                Path to be examined
                Ensure that multiple lines are indented correctly.

            Ensure that multiple lines are indented correctly.
            Ensure that multiple lines are indented correctly.
        """)

    def test_docstring_trailing_whitespace(self):
        function = self.parse_function(
            "module t\n"
            "t.s\n"
            "   a: object\n"
            "      Param docstring with trailing whitespace  \n"
            "Func docstring summary with trailing whitespace  \n"
            "  \n"
            "Func docstring body with trailing whitespace  \n"
        )
        self.checkDocstring(function, """
            s($module, /, a)
            --

            Func docstring summary with trailing whitespace

              a
                Param docstring with trailing whitespace

            Func docstring body with trailing whitespace
        """)

    def test_explicit_parameters_in_docstring(self):
        function = self.parse_function(dedent("""
            module foo
            foo.bar
              x: int
                 Documentation for x.
              y: int

            This is the documentation for foo.

            Okay, we're done here.
        """))
        self.checkDocstring(function, """
            bar($module, /, x, y)
            --

            This is the documentation for foo.

              x
                Documentation for x.

            Okay, we're done here.
        """)

    def test_docstring_with_comments(self):
        function = self.parse_function(dedent("""
            module foo
            foo.bar
              x: int
                 # We're about to have
                 # the documentation for x.
                 Documentation for x.
                 # We've just had
                 # the documentation for x.
              y: int

            # We're about to have
            # the documentation for foo.
            This is the documentation for foo.
            # We've just had
            # the documentation for foo.

            Okay, we're done here.
        """))
        self.checkDocstring(function, """
            bar($module, /, x, y)
            --

            This is the documentation for foo.

              x
                Documentation for x.

            Okay, we're done here.
        """)

    def test_parser_regression_special_character_in_parameter_column_of_docstring_first_line(self):
        function = self.parse_function(dedent("""
            module os
            os.stat
                path: str
            This/used to break Clinic!
        """))
        self.checkDocstring(function, """
            stat($module, /, path)
            --

            This/used to break Clinic!
        """)

    def test_c_name(self):
        function = self.parse_function("""
            module os
            os.stat as os_stat_fn
        """)
        self.assertEqual("os_stat_fn", function.c_basename)

    def test_base_invalid_syntax(self):
        block = """
            module os
            os.stat
                invalid syntax: int = 42
        """
        err = dedent(r"""
            Function 'stat' has an invalid parameter declaration:
            \s+'invalid syntax: int = 42'
        """).strip()
        with self.assertRaisesRegex(clinic.ClinicError, err):
            self.parse_function(block)

    def test_param_default_invalid_syntax(self):
        block = """
            module os
            os.stat
                x: int = invalid syntax
        """
        err = r"Syntax error: 'x = invalid syntax\n'"
        self.expect_failure(block, err, lineno=2)

    def test_cloning_nonexistent_function_correctly_fails(self):
        block = """
            cloned = fooooooooooooooooo
            This is trying to clone a nonexistent function!!
        """
        err = "Couldn't find existing function 'fooooooooooooooooo'!"
        with support.captured_stderr() as stderr:
            self.expect_failure(block, err, lineno=0)
        expected_debug_print = dedent("""\
            cls=None, module=<clinic.Clinic object>, existing='fooooooooooooooooo'
            (cls or module).functions=[]
        """)
        stderr = stderr.getvalue()
        self.assertIn(expected_debug_print, stderr)

    def test_return_converter(self):
        function = self.parse_function("""
            module os
            os.stat -> int
        """)
        self.assertIsInstance(function.return_converter, clinic.int_return_converter)

    def test_return_converter_invalid_syntax(self):
        block = """
            module os
            os.stat -> invalid syntax
        """
        err = "Badly formed annotation for 'os.stat': 'invalid syntax'"
        self.expect_failure(block, err)

    def test_legacy_converter_disallowed_in_return_annotation(self):
        block = """
            module os
            os.stat -> "s"
        """
        err = "Legacy converter 's' not allowed as a return converter"
        self.expect_failure(block, err)

    def test_unknown_return_converter(self):
        block = """
            module os
            os.stat -> fooooooooooooooooooooooo
        """
        err = "No available return converter called 'fooooooooooooooooooooooo'"
        self.expect_failure(block, err)

    def test_star(self):
        function = self.parse_function("""
            module os
            os.access
                *
                follow_symlinks: bool = True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(inspect.Parameter.KEYWORD_ONLY, p.kind)
        self.assertEqual(0, p.group)

    def test_group(self):
        function = self.parse_function("""
            module window
            window.border
                [
                ls: int
                ]
                /
        """)
        p = function.parameters['ls']
        self.assertEqual(1, p.group)

    def test_left_group(self):
        function = self.parse_function("""
            module curses
            curses.addch
                [
                y: int
                    Y-coordinate.
                x: int
                    X-coordinate.
                ]
                ch: char
                    Character to add.
                [
                attr: long
                    Attributes for the character.
                ]
                /
        """)
        dataset = (
            ('y', -1), ('x', -1),
            ('ch', 0),
            ('attr', 1),
        )
        for name, group in dataset:
            with self.subTest(name=name, group=group):
                p = function.parameters[name]
                self.assertEqual(p.group, group)
                self.assertEqual(p.kind, inspect.Parameter.POSITIONAL_ONLY)
        self.checkDocstring(function, """
            addch([y, x,] ch, [attr])


              y
                Y-coordinate.
              x
                X-coordinate.
              ch
                Character to add.
              attr
                Attributes for the character.
        """)

    def test_nested_groups(self):
        function = self.parse_function("""
            module curses
            curses.imaginary
               [
               [
               y1: int
                 Y-coordinate.
               y2: int
                 Y-coordinate.
               ]
               x1: int
                 X-coordinate.
               x2: int
                 X-coordinate.
               ]
               ch: char
                 Character to add.
               [
               attr1: long
                 Attributes for the character.
               attr2: long
                 Attributes for the character.
               attr3: long
                 Attributes for the character.
               [
               attr4: long
                 Attributes for the character.
               attr5: long
                 Attributes for the character.
               attr6: long
                 Attributes for the character.
               ]
               ]
               /
        """)
        dataset = (
            ('y1', -2), ('y2', -2),
            ('x1', -1), ('x2', -1),
            ('ch', 0),
            ('attr1', 1), ('attr2', 1), ('attr3', 1),
            ('attr4', 2), ('attr5', 2), ('attr6', 2),
        )
        for name, group in dataset:
            with self.subTest(name=name, group=group):
                p = function.parameters[name]
                self.assertEqual(p.group, group)
                self.assertEqual(p.kind, inspect.Parameter.POSITIONAL_ONLY)

        self.checkDocstring(function, """
            imaginary([[y1, y2,] x1, x2,] ch, [attr1, attr2, attr3, [attr4, attr5,
                      attr6]])


              y1
                Y-coordinate.
              y2
                Y-coordinate.
              x1
                X-coordinate.
              x2
                X-coordinate.
              ch
                Character to add.
              attr1
                Attributes for the character.
              attr2
                Attributes for the character.
              attr3
                Attributes for the character.
              attr4
                Attributes for the character.
              attr5
                Attributes for the character.
              attr6
                Attributes for the character.
        """)

    def test_disallowed_grouping__two_top_groups_on_left(self):
        err = (
            "Function 'two_top_groups_on_left' has an unsupported group "
            "configuration. (Unexpected state 2.b)"
        )
        block = """
            module foo
            foo.two_top_groups_on_left
                [
                group1 : int
                ]
                [
                group2 : int
                ]
                param: int
        """
        self.expect_failure(block, err, lineno=5)

    def test_disallowed_grouping__two_top_groups_on_right(self):
        block = """
            module foo
            foo.two_top_groups_on_right
                param: int
                [
                group1 : int
                ]
                [
                group2 : int
                ]
        """
        err = (
            "Function 'two_top_groups_on_right' has an unsupported group "
            "configuration. (Unexpected state 6.b)"
        )
        self.expect_failure(block, err)

    def test_disallowed_grouping__parameter_after_group_on_right(self):
        block = """
            module foo
            foo.parameter_after_group_on_right
                param: int
                [
                [
                group1 : int
                ]
                group2 : int
                ]
        """
        err = (
            "Function parameter_after_group_on_right has an unsupported group "
            "configuration. (Unexpected state 6.a)"
        )
        self.expect_failure(block, err)

    def test_disallowed_grouping__group_after_parameter_on_left(self):
        block = """
            module foo
            foo.group_after_parameter_on_left
                [
                group2 : int
                [
                group1 : int
                ]
                ]
                param: int
        """
        err = (
            "Function 'group_after_parameter_on_left' has an unsupported group "
            "configuration. (Unexpected state 2.b)"
        )
        self.expect_failure(block, err)

    def test_disallowed_grouping__empty_group_on_left(self):
        block = """
            module foo
            foo.empty_group
                [
                [
                ]
                group2 : int
                ]
                param: int
        """
        err = (
            "Function 'empty_group' has an empty group. "
            "All groups must contain at least one parameter."
        )
        self.expect_failure(block, err)

    def test_disallowed_grouping__empty_group_on_right(self):
        block = """
            module foo
            foo.empty_group
                param: int
                [
                [
                ]
                group2 : int
                ]
        """
        err = (
            "Function 'empty_group' has an empty group. "
            "All groups must contain at least one parameter."
        )
        self.expect_failure(block, err)

    def test_disallowed_grouping__no_matching_bracket(self):
        block = """
            module foo
            foo.empty_group
                param: int
                ]
                group2: int
                ]
        """
        err = "Function 'empty_group' has a ']' without a matching '['"
        self.expect_failure(block, err)

    def test_no_parameters(self):
        function = self.parse_function("""
            module foo
            foo.bar

            Docstring

        """)
        self.assertEqual("bar($module, /)\n--\n\nDocstring", function.docstring)
        self.assertEqual(1, len(function.parameters)) # self!

    def test_init_with_no_parameters(self):
        function = self.parse_function("""
            module foo
            class foo.Bar "unused" "notneeded"
            foo.Bar.__init__

            Docstring

        """, signatures_in_block=3, function_index=2)

        # self is not in the signature
        self.assertEqual("Bar()\n--\n\nDocstring", function.docstring)
        # but it *is* a parameter
        self.assertEqual(1, len(function.parameters))

    def test_illegal_module_line(self):
        block = """
            module foo
            foo.bar => int
                /
        """
        err = "Illegal function name: 'foo.bar => int'"
        self.expect_failure(block, err)

    def test_illegal_c_basename(self):
        block = """
            module foo
            foo.bar as 935
                /
        """
        err = "Illegal C basename: '935'"
        self.expect_failure(block, err)

    def test_single_star(self):
        block = """
            module foo
            foo.bar
                *
                *
        """
        err = "Function 'bar' uses '*' more than once."
        self.expect_failure(block, err)

    def test_parameters_required_after_star(self):
        dataset = (
            "module foo\nfoo.bar\n  *",
            "module foo\nfoo.bar\n  *\nDocstring here.",
            "module foo\nfoo.bar\n  this: int\n  *",
            "module foo\nfoo.bar\n  this: int\n  *\nDocstring.",
        )
        err = "Function 'foo.bar' specifies '*' without any parameters afterwards."
        for block in dataset:
            with self.subTest(block=block):
                self.expect_failure(block, err)

    def test_fulldisplayname_class(self):
        dataset = (
            ("T", """
                class T "void *" ""
                T.__init__
            """),
            ("m.T", """
                module m
                class m.T "void *" ""
                @classmethod
                m.T.__new__
            """),
            ("m.T.C", """
                module m
                class m.T "void *" ""
                class m.T.C "void *" ""
                m.T.C.__init__
            """),
        )
        for name, code in dataset:
            with self.subTest(name=name, code=code):
                block = self.parse(code)
                func = block.signatures[-1]
                self.assertEqual(func.fulldisplayname, name)

    def test_fulldisplayname_meth(self):
        dataset = (
            ("func", "func"),
            ("m.func", """
                module m
                m.func
            """),
            ("T.meth", """
                class T "void *" ""
                T.meth
            """),
            ("m.T.meth", """
                module m
                class m.T "void *" ""
                m.T.meth
            """),
            ("m.T.C.meth", """
                module m
                class m.T "void *" ""
                class m.T.C "void *" ""
                m.T.C.meth
            """),
        )
        for name, code in dataset:
            with self.subTest(name=name, code=code):
                block = self.parse(code)
                func = block.signatures[-1]
                self.assertEqual(func.fulldisplayname, name)

    def test_depr_star_invalid_format_1(self):
        block = """
            module foo
            foo.bar
                this: int
                * [from 3]
            Docstring.
        """
        err = (
            "Function 'foo.bar': expected format '* [from major.minor]' "
            "where 'major' and 'minor' are integers; got '3'"
        )
        self.expect_failure(block, err, lineno=3)

    def test_depr_star_invalid_format_2(self):
        block = """
            module foo
            foo.bar
                this: int
                * [from a.b]
            Docstring.
        """
        err = (
            "Function 'foo.bar': expected format '* [from major.minor]' "
            "where 'major' and 'minor' are integers; got 'a.b'"
        )
        self.expect_failure(block, err, lineno=3)

    def test_depr_star_invalid_format_3(self):
        block = """
            module foo
            foo.bar
                this: int
                * [from 1.2.3]
            Docstring.
        """
        err = (
            "Function 'foo.bar': expected format '* [from major.minor]' "
            "where 'major' and 'minor' are integers; got '1.2.3'"
        )
        self.expect_failure(block, err, lineno=3)

    def test_parameters_required_after_depr_star(self):
        block = """
            module foo
            foo.bar
                this: int
                * [from 3.14]
            Docstring.
        """
        err = (
            "Function 'foo.bar' specifies '* [from ...]' without "
            "any parameters afterwards"
        )
        self.expect_failure(block, err, lineno=4)

    def test_depr_star_must_come_before_star(self):
        block = """
            module foo
            foo.bar
                this: int
                *
                * [from 3.14]
            Docstring.
        """
        err = "Function 'foo.bar': '* [from ...]' must come before '*'"
        self.expect_failure(block, err, lineno=4)

    def test_depr_star_duplicate(self):
        block = """
            module foo
            foo.bar
                a: int
                * [from 3.14]
                b: int
                * [from 3.14]
                c: int
            Docstring.
        """
        err = "Function 'foo.bar' uses '[from ...]' more than once"
        self.expect_failure(block, err, lineno=5)

    def test_single_slash(self):
        block = """
            module foo
            foo.bar
                /
                /
        """
        err = (
            "Function 'bar' has an unsupported group configuration. "
            "(Unexpected state 0.d)"
        )
        self.expect_failure(block, err)

    def test_double_slash(self):
        block = """
            module foo
            foo.bar
                a: int
                /
                b: int
                /
        """
        err = "Function 'bar' uses '/' more than once."
        self.expect_failure(block, err)

    def test_mix_star_and_slash(self):
        block = """
            module foo
            foo.bar
               x: int
               y: int
               *
               z: int
               /
        """
        err = (
            "Function 'bar' mixes keyword-only and positional-only parameters, "
            "which is unsupported."
        )
        self.expect_failure(block, err)

    def test_parameters_not_permitted_after_slash_for_now(self):
        block = """
            module foo
            foo.bar
                /
                x: int
        """
        err = (
            "Function 'bar' has an unsupported group configuration. "
            "(Unexpected state 0.d)"
        )
        self.expect_failure(block, err)

    def test_parameters_no_more_than_one_vararg(self):
        err = "Too many var args"
        block = """
            module foo
            foo.bar
               *vararg1: object
               *vararg2: object
        """
        self.expect_failure(block, err, lineno=0)

    def test_function_not_at_column_0(self):
        function = self.parse_function("""
              module foo
              foo.bar
                x: int
                  Nested docstring here, goeth.
                *
                y: str
              Not at column 0!
        """)
        self.checkDocstring(function, """
            bar($module, /, x, *, y)
            --

            Not at column 0!

              x
                Nested docstring here, goeth.
        """)

    def test_docstring_only_summary(self):
        function = self.parse_function("""
              module m
              m.f
              summary
        """)
        self.checkDocstring(function, """
            f($module, /)
            --

            summary
        """)

    def test_docstring_empty_lines(self):
        function = self.parse_function("""
              module m
              m.f


        """)
        self.checkDocstring(function, """
            f($module, /)
            --
        """)

    def test_docstring_explicit_params_placement(self):
        function = self.parse_function("""
              module m
              m.f
                a: int
                    Param docstring for 'a' will be included
                b: int
                c: int
                    Param docstring for 'c' will be included
              This is the summary line.

              We'll now place the params section here:
              {parameters}
              And now for something completely different!
              (Note the added newline)
        """)
        self.checkDocstring(function, """
            f($module, /, a, b, c)
            --

            This is the summary line.

            We'll now place the params section here:
              a
                Param docstring for 'a' will be included
              c
                Param docstring for 'c' will be included

            And now for something completely different!
            (Note the added newline)
        """)

    def test_indent_stack_no_tabs(self):
        block = """
            module foo
            foo.bar
               *vararg1: object
            \t*vararg2: object
        """
        err = ("Tab characters are illegal in the Clinic DSL: "
               r"'\t*vararg2: object'")
        self.expect_failure(block, err)

    def test_indent_stack_illegal_outdent(self):
        block = """
            module foo
            foo.bar
              a: object
             b: object
        """
        err = "Illegal outdent"
        self.expect_failure(block, err)

    def test_directive(self):
        parser = DSLParser(_make_clinic())
        parser.flag = False
        parser.directives['setflag'] = lambda : setattr(parser, 'flag', True)
        block = clinic.Block("setflag")
        parser.parse(block)
        self.assertTrue(parser.flag)

    def test_legacy_converters(self):
        block = self.parse('module os\nos.access\n   path: "s"')
        module, function = block.signatures
        conv = (function.parameters['path']).converter
        self.assertIsInstance(conv, clinic.str_converter)

    def test_legacy_converters_non_string_constant_annotation(self):
        err = "Annotations must be either a name, a function call, or a string"
        dataset = (
            'module os\nos.access\n   path: 42',
            'module os\nos.access\n   path: 42.42',
            'module os\nos.access\n   path: 42j',
            'module os\nos.access\n   path: b"42"',
        )
        for block in dataset:
            with self.subTest(block=block):
                self.expect_failure(block, err, lineno=2)

    def test_other_bizarre_things_in_annotations_fail(self):
        err = "Annotations must be either a name, a function call, or a string"
        dataset = (
            'module os\nos.access\n   path: {"some": "dictionary"}',
            'module os\nos.access\n   path: ["list", "of", "strings"]',
            'module os\nos.access\n   path: (x for x in range(42))',
        )
        for block in dataset:
            with self.subTest(block=block):
                self.expect_failure(block, err, lineno=2)

    def test_kwarg_splats_disallowed_in_function_call_annotations(self):
        err = "Cannot use a kwarg splat in a function-call annotation"
        dataset = (
            'module fo\nfo.barbaz\n   o: bool(**{None: "bang!"})',
            'module fo\nfo.barbaz -> bool(**{None: "bang!"})',
            'module fo\nfo.barbaz -> bool(**{"bang": 42})',
            'module fo\nfo.barbaz\n   o: bool(**{"bang": None})',
        )
        for block in dataset:
            with self.subTest(block=block):
                self.expect_failure(block, err)

    def test_self_param_placement(self):
        err = (
            "A 'self' parameter, if specified, must be the very first thing "
            "in the parameter block."
        )
        block = """
            module foo
            foo.func
                a: int
                self: self(type="PyObject *")
        """
        self.expect_failure(block, err, lineno=3)

    def test_self_param_cannot_be_optional(self):
        err = "A 'self' parameter cannot be marked optional."
        block = """
            module foo
            foo.func
                self: self(type="PyObject *") = None
        """
        self.expect_failure(block, err, lineno=2)

    def test_defining_class_param_placement(self):
        err = (
            "A 'defining_class' parameter, if specified, must either be the "
            "first thing in the parameter block, or come just after 'self'."
        )
        block = """
            module foo
            foo.func
                self: self(type="PyObject *")
                a: int
                cls: defining_class
        """
        self.expect_failure(block, err, lineno=4)

    def test_defining_class_param_cannot_be_optional(self):
        err = "A 'defining_class' parameter cannot be marked optional."
        block = """
            module foo
            foo.func
                cls: defining_class(type="PyObject *") = None
        """
        self.expect_failure(block, err, lineno=2)

    def test_slot_methods_cannot_access_defining_class(self):
        block = """
            module foo
            class Foo "" ""
            Foo.__init__
                cls: defining_class
                a: object
        """
        err = "Slot methods cannot access their defining class."
        with self.assertRaisesRegex(ValueError, err):
            self.parse_function(block)

    def test_new_must_be_a_class_method(self):
        err = "__new__ must be a class method!"
        block = """
            module foo
            class Foo "" ""
            Foo.__new__
        """
        self.expect_failure(block, err, lineno=2)

    def test_init_must_be_a_normal_method(self):
        err = "__init__ must be a normal method, not a class or static method!"
        block = """
            module foo
            class Foo "" ""
            @classmethod
            Foo.__init__
        """
        self.expect_failure(block, err, lineno=3)

    def test_duplicate_coexist(self):
        err = "Called @coexist twice"
        block = """
            module m
            @coexist
            @coexist
            m.fn
        """
        self.expect_failure(block, err, lineno=2)

    def test_unused_param(self):
        block = self.parse("""
            module foo
            foo.func
                fn: object
                k: float
                i: float(unused=True)
                /
                *
                flag: bool(unused=True) = False
        """)
        sig = block.signatures[1]  # Function index == 1
        params = sig.parameters
        conv = lambda fn: params[fn].converter
        dataset = (
            {"name": "fn", "unused": False},
            {"name": "k", "unused": False},
            {"name": "i", "unused": True},
            {"name": "flag", "unused": True},
        )
        for param in dataset:
            name, unused = param.values()
            with self.subTest(name=name, unused=unused):
                p = conv(name)
                # Verify that the unused flag is parsed correctly.
                self.assertEqual(unused, p.unused)

                # Now, check that we'll produce correct code.
                decl = p.simple_declaration(in_parser=False)
                if unused:
                    self.assertIn("Py_UNUSED", decl)
                else:
                    self.assertNotIn("Py_UNUSED", decl)

                # Make sure the Py_UNUSED macro is not used in the parser body.
                parser_decl = p.simple_declaration(in_parser=True)
                self.assertNotIn("Py_UNUSED", parser_decl)

    def test_scaffolding(self):
        # test repr on special values
        self.assertEqual(repr(clinic.unspecified), '<Unspecified>')
        self.assertEqual(repr(clinic.NULL), '<Null>')

        # test that fail fails
        with support.captured_stdout() as stdout:
            errmsg = 'The igloos are melting'
            with self.assertRaisesRegex(clinic.ClinicError, errmsg) as cm:
                clinic.fail(errmsg, filename='clown.txt', line_number=69)
            exc = cm.exception
            self.assertEqual(exc.filename, 'clown.txt')
            self.assertEqual(exc.lineno, 69)
            self.assertEqual(stdout.getvalue(), "")

    def test_non_ascii_character_in_docstring(self):
        block = """
            module test
            test.fn
                a: int
                    á param docstring
            docstring fü bár baß
        """
        with support.captured_stdout() as stdout:
            self.parse(block)
        # The line numbers are off; this is a known limitation.
        expected = dedent("""\
            Warning in file 'clinic_tests' on line 0:
            Non-ascii characters are not allowed in docstrings: 'á'

            Warning in file 'clinic_tests' on line 0:
            Non-ascii characters are not allowed in docstrings: 'ü', 'á', 'ß'

        """)
        self.assertEqual(stdout.getvalue(), expected)

    def test_illegal_c_identifier(self):
        err = "Illegal C identifier: 17a"
        block = """
            module test
            test.fn
                a as 17a: int
        """
        self.expect_failure(block, err, lineno=2)

    def test_cannot_convert_special_method(self):
        err = "__len__ is a special method and cannot be converted"
        block = """
            class T "" ""
            T.__len__
        """
        self.expect_failure(block, err, lineno=1)

    def test_cannot_specify_pydefault_without_default(self):
        err = "You can't specify py_default without specifying a default value!"
        block = """
            fn
                a: object(py_default='NULL')
        """
        self.expect_failure(block, err, lineno=1)

    def test_vararg_cannot_take_default_value(self):
        err = "Vararg can't take a default value!"
        block = """
            fn
                *args: object = None
        """
        self.expect_failure(block, err, lineno=1)

    def test_default_is_not_of_correct_type(self):
        err = ("int_converter: default value 2.5 for field 'a' "
               "is not of type 'int'")
        block = """
            fn
                a: int = 2.5
        """
        self.expect_failure(block, err, lineno=1)

    def test_invalid_legacy_converter(self):
        err = "'fhi' is not a valid legacy converter"
        block = """
            fn
                a: 'fhi'
        """
        self.expect_failure(block, err, lineno=1)

    def test_parent_class_or_module_does_not_exist(self):
        err = "Parent class or module 'z' does not exist"
        block = """
            module m
            z.func
        """
        self.expect_failure(block, err, lineno=1)

    def test_duplicate_param_name(self):
        err = "You can't have two parameters named 'a'"
        block = """
            module m
            m.func
                a: int
                a: float
        """
        self.expect_failure(block, err, lineno=3)

    def test_param_requires_custom_c_name(self):
        err = "Parameter 'module' requires a custom C name"
        block = """
            module m
            m.func
                module: int
        """
        self.expect_failure(block, err, lineno=2)

    def test_state_func_docstring_assert_no_group(self):
        err = "Function 'func' has a ']' without a matching '['"
        block = """
            module m
            m.func
                ]
            docstring
        """
        self.expect_failure(block, err, lineno=2)

    def test_state_func_docstring_no_summary(self):
        err = "Docstring for 'm.func' does not have a summary line!"
        block = """
            module m
            m.func
            docstring1
            docstring2
        """
        self.expect_failure(block, err, lineno=0)

    def test_state_func_docstring_only_one_param_template(self):
        err = "You may not specify {parameters} more than once in a docstring!"
        block = """
            module m
            m.func
            docstring summary

            these are the params:
                {parameters}
            these are the params again:
                {parameters}
        """
        self.expect_failure(block, err, lineno=0)


class ClinicExternalTest(TestCase):
    maxDiff = None

    def run_clinic(self, *args):
        with (
            support.captured_stdout() as out,
            support.captured_stderr() as err,
            self.assertRaises(SystemExit) as cm
        ):
            clinic.main(args)
        return out.getvalue(), err.getvalue(), cm.exception.code

    def expect_success(self, *args):
        out, err, code = self.run_clinic(*args)
        if code != 0:
            self.fail("\n".join([f"Unexpected failure: {args=}", out, err]))
        self.assertEqual(err, "")
        return out

    def expect_failure(self, *args):
        out, err, code = self.run_clinic(*args)
        self.assertNotEqual(code, 0, f"Unexpected success: {args=}")
        return out, err

    def test_external(self):
        CLINIC_TEST = 'clinic.test.c'
        source = support.findfile(CLINIC_TEST)
        with open(source, 'r', encoding='utf-8') as f:
            orig_contents = f.read()

        # Run clinic CLI and verify that it does not complain.
        self.addCleanup(unlink, TESTFN)
        out = self.expect_success("-f", "-o", TESTFN, source)
        self.assertEqual(out, "")

        with open(TESTFN, 'r', encoding='utf-8') as f:
            new_contents = f.read()

        self.assertEqual(new_contents, orig_contents)

    def test_no_change(self):
        # bpo-42398: Test that the destination file is left unchanged if the
        # content does not change. Moreover, check also that the file
        # modification time does not change in this case.
        code = dedent("""
            /*[clinic input]
            [clinic start generated code]*/
            /*[clinic end generated code: output=da39a3ee5e6b4b0d input=da39a3ee5e6b4b0d]*/
        """)
        with os_helper.temp_dir() as tmp_dir:
            fn = os.path.join(tmp_dir, "test.c")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(code)
            pre_mtime = os.stat(fn).st_mtime_ns
            self.expect_success(fn)
            post_mtime = os.stat(fn).st_mtime_ns
        # Don't change the file modification time
        # if the content does not change
        self.assertEqual(pre_mtime, post_mtime)

    def test_cli_force(self):
        invalid_input = dedent("""
            /*[clinic input]
            output preset block
            module test
            test.fn
                a: int
            [clinic start generated code]*/

            const char *hand_edited = "output block is overwritten";
            /*[clinic end generated code: output=bogus input=bogus]*/
        """)
        fail_msg = (
            "Checksum mismatch! Expected 'bogus', computed '2ed19'. "
            "Suggested fix: remove all generated code including the end marker, "
            "or use the '-f' option.\n"
        )
        with os_helper.temp_dir() as tmp_dir:
            fn = os.path.join(tmp_dir, "test.c")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(invalid_input)
            # First, run the CLI without -f and expect failure.
            # Note, we cannot check the entire fail msg, because the path to
            # the tmp file will change for every run.
            _, err = self.expect_failure(fn)
            self.assertTrue(err.endswith(fail_msg),
                            f"{err!r} does not end with {fail_msg!r}")
            # Then, force regeneration; success expected.
            out = self.expect_success("-f", fn)
            self.assertEqual(out, "")
            # Verify by checking the checksum.
            checksum = (
                "/*[clinic end generated code: "
                "output=2124c291eb067d76 input=9543a8d2da235301]*/\n"
            )
            with open(fn, 'r', encoding='utf-8') as f:
                generated = f.read()
            self.assertTrue(generated.endswith(checksum))

    def test_cli_make(self):
        c_code = dedent("""
            /*[clinic input]
            [clinic start generated code]*/
        """)
        py_code = "pass"
        c_files = "file1.c", "file2.c"
        py_files = "file1.py", "file2.py"

        def create_files(files, srcdir, code):
            for fn in files:
                path = os.path.join(srcdir, fn)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)

        with os_helper.temp_dir() as tmp_dir:
            # add some folders, some C files and a Python file
            create_files(c_files, tmp_dir, c_code)
            create_files(py_files, tmp_dir, py_code)

            # create C files in externals/ dir
            ext_path = os.path.join(tmp_dir, "externals")
            with os_helper.temp_dir(path=ext_path) as externals:
                create_files(c_files, externals, c_code)

                # run clinic in verbose mode with --make on tmpdir
                out = self.expect_success("-v", "--make", "--srcdir", tmp_dir)

            # expect verbose mode to only mention the C files in tmp_dir
            for filename in c_files:
                with self.subTest(filename=filename):
                    path = os.path.join(tmp_dir, filename)
                    self.assertIn(path, out)
            for filename in py_files:
                with self.subTest(filename=filename):
                    path = os.path.join(tmp_dir, filename)
                    self.assertNotIn(path, out)
            # don't expect C files from the externals dir
            for filename in c_files:
                with self.subTest(filename=filename):
                    path = os.path.join(ext_path, filename)
                    self.assertNotIn(path, out)

    def test_cli_make_exclude(self):
        code = dedent("""
            /*[clinic input]
            [clinic start generated code]*/
        """)
        with os_helper.temp_dir(quiet=False) as tmp_dir:
            # add some folders, some C files and a Python file
            for fn in "file1.c", "file2.c", "file3.c", "file4.c":
                path = os.path.join(tmp_dir, fn)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)

            # Run clinic in verbose mode with --make on tmpdir.
            # Exclude file2.c and file3.c.
            out = self.expect_success(
                "-v", "--make", "--srcdir", tmp_dir,
                "--exclude", os.path.join(tmp_dir, "file2.c"),
                # The added ./ should be normalised away.
                "--exclude", os.path.join(tmp_dir, "./file3.c"),
                # Relative paths should also work.
                "--exclude", "file4.c"
            )

            # expect verbose mode to only mention the C files in tmp_dir
            self.assertIn("file1.c", out)
            self.assertNotIn("file2.c", out)
            self.assertNotIn("file3.c", out)
            self.assertNotIn("file4.c", out)

    def test_cli_verbose(self):
        with os_helper.temp_dir() as tmp_dir:
            fn = os.path.join(tmp_dir, "test.c")
            with open(fn, "w", encoding="utf-8") as f:
                f.write("")
            out = self.expect_success("-v", fn)
            self.assertEqual(out.strip(), fn)

    def test_cli_help(self):
        out = self.expect_success("-h")
        self.assertIn("usage: clinic.py", out)

    def test_cli_converters(self):
        prelude = dedent("""
            Legacy converters:
                B C D L O S U Y Z Z#
                b c d f h i l p s s# s* u u# w* y y# y* z z# z*

            Converters:
        """)
        expected_converters = (
            "bool",
            "byte",
            "char",
            "defining_class",
            "double",
            "fildes",
            "float",
            "int",
            "long",
            "long_long",
            "object",
            "Py_buffer",
            "Py_complex",
            "Py_ssize_t",
            "Py_UNICODE",
            "PyByteArrayObject",
            "PyBytesObject",
            "self",
            "short",
            "size_t",
            "slice_index",
            "str",
            "unicode",
            "unsigned_char",
            "unsigned_int",
            "unsigned_long",
            "unsigned_long_long",
            "unsigned_short",
        )
        finale = dedent("""
            Return converters:
                bool()
                double()
                float()
                init()
                int()
                long()
                Py_ssize_t()
                size_t()
                unsigned_int()
                unsigned_long()

            All converters also accept (c_default=None, py_default=None, annotation=None).
            All return converters also accept (py_default=None).
        """)
        out = self.expect_success("--converters")
        # We cannot simply compare the output, because the repr of the *accept*
        # param may change (it's a set, thus unordered). So, let's compare the
        # start and end of the expected output, and then assert that the
        # converters appear lined up in alphabetical order.
        self.assertTrue(out.startswith(prelude), out)
        self.assertTrue(out.endswith(finale), out)

        out = out.removeprefix(prelude)
        out = out.removesuffix(finale)
        lines = out.split("\n")
        for converter, line in zip(expected_converters, lines):
            line = line.lstrip()
            with self.subTest(converter=converter):
                self.assertTrue(
                    line.startswith(converter),
                    f"expected converter {converter!r}, got {line!r}"
                )

    def test_cli_fail_converters_and_filename(self):
        _, err = self.expect_failure("--converters", "test.c")
        msg = "can't specify --converters and a filename at the same time"
        self.assertIn(msg, err)

    def test_cli_fail_no_filename(self):
        _, err = self.expect_failure()
        self.assertIn("no input files", err)

    def test_cli_fail_output_and_multiple_files(self):
        _, err = self.expect_failure("-o", "out.c", "input.c", "moreinput.c")
        msg = "error: can't use -o with multiple filenames"
        self.assertIn(msg, err)

    def test_cli_fail_filename_or_output_and_make(self):
        msg = "can't use -o or filenames with --make"
        for opts in ("-o", "out.c"), ("filename.c",):
            with self.subTest(opts=opts):
                _, err = self.expect_failure("--make", *opts)
                self.assertIn(msg, err)

    def test_cli_fail_make_without_srcdir(self):
        _, err = self.expect_failure("--make", "--srcdir", "")
        msg = "error: --srcdir must not be empty with --make"
        self.assertIn(msg, err)

    def test_file_dest(self):
        block = dedent("""
            /*[clinic input]
            destination test new file {path}.h
            output everything test
            func
                a: object
                /
            [clinic start generated code]*/
        """)
        expected_checksum_line = (
            "/*[clinic end generated code: "
            "output=da39a3ee5e6b4b0d input=b602ab8e173ac3bd]*/\n"
        )
        expected_output = dedent("""\
            /*[clinic input]
            preserve
            [clinic start generated code]*/

            #if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)
            #  include "pycore_gc.h"            // PyGC_Head
            #  include "pycore_runtime.h"       // _Py_ID()
            #endif


            PyDoc_VAR(func__doc__);

            PyDoc_STRVAR(func__doc__,
            "func($module, a, /)\\n"
            "--\\n"
            "\\n");

            #define FUNC_METHODDEF    \\
                {"func", (PyCFunction)func, METH_O, func__doc__},

            static PyObject *
            func(PyObject *module, PyObject *a)
            /*[clinic end generated code: output=56c09670e89a0d9a input=a9049054013a1b77]*/
        """)
        with os_helper.temp_dir() as tmp_dir:
            in_fn = os.path.join(tmp_dir, "test.c")
            out_fn = os.path.join(tmp_dir, "test.c.h")
            with open(in_fn, "w", encoding="utf-8") as f:
                f.write(block)
            with open(out_fn, "w", encoding="utf-8") as f:
                f.write("")  # Write an empty output file!
            # Clinic should complain about the empty output file.
            _, err = self.expect_failure(in_fn)
            expected_err = (f"Modified destination file {out_fn!r}; "
                            "not overwriting!")
            self.assertIn(expected_err, err)
            # Run clinic again, this time with the -f option.
            _ = self.expect_success("-f", in_fn)
            # Read back the generated output.
            with open(in_fn, encoding="utf-8") as f:
                data = f.read()
                expected_block = f"{block}{expected_checksum_line}"
                self.assertEqual(data, expected_block)
            with open(out_fn, encoding="utf-8") as f:
                data = f.read()
                self.assertEqual(data, expected_output)

try:
    import _testclinic as ac_tester
except ImportError:
    ac_tester = None

@unittest.skipIf(ac_tester is None, "_testclinic is missing")
class ClinicFunctionalTest(unittest.TestCase):
    locals().update((name, getattr(ac_tester, name))
                    for name in dir(ac_tester) if name.startswith('test_'))

    def check_depr_star(self, pnames, fn, *args, **kwds):
        regex = (
            fr"Passing( more than)?( [0-9]+)? positional argument(s)? to "
            fr"{fn.__name__}\(\) is deprecated. Parameter(s)? {pnames} will "
            fr"become( a)? keyword-only parameter(s)? in Python 3\.14"
        )
        with self.assertWarnsRegex(DeprecationWarning, regex) as cm:
            # Record the line number, so we're sure we've got the correct stack
            # level on the deprecation warning.
            _, lineno = fn(*args, **kwds), sys._getframe().f_lineno
        self.assertEqual(cm.filename, __file__)
        self.assertEqual(cm.lineno, lineno)

    def test_objects_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.objects_converter()
        self.assertEqual(ac_tester.objects_converter(1, 2), (1, 2))
        self.assertEqual(ac_tester.objects_converter([], 'whatever class'), ([], 'whatever class'))
        self.assertEqual(ac_tester.objects_converter(1), (1, None))

    def test_bytes_object_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.bytes_object_converter(1)
        self.assertEqual(ac_tester.bytes_object_converter(b'BytesObject'), (b'BytesObject',))

    def test_byte_array_object_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.byte_array_object_converter(1)
        byte_arr = bytearray(b'ByteArrayObject')
        self.assertEqual(ac_tester.byte_array_object_converter(byte_arr), (byte_arr,))

    def test_unicode_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.unicode_converter(1)
        self.assertEqual(ac_tester.unicode_converter('unicode'), ('unicode',))

    def test_bool_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.bool_converter(False, False, 'not a int')
        self.assertEqual(ac_tester.bool_converter(), (True, True, True))
        self.assertEqual(ac_tester.bool_converter('', [], 5), (False, False, True))
        self.assertEqual(ac_tester.bool_converter(('not empty',), {1: 2}, 0), (True, True, False))

    def test_char_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.char_converter(1)
        with self.assertRaises(TypeError):
            ac_tester.char_converter(b'ab')
        chars = [b'A', b'\a', b'\b', b'\t', b'\n', b'\v', b'\f', b'\r', b'"', b"'", b'?', b'\\', b'\000', b'\377']
        expected = tuple(ord(c) for c in chars)
        self.assertEqual(ac_tester.char_converter(), expected)
        chars = [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9', b'0', b'a', b'b', b'c', b'd']
        expected = tuple(ord(c) for c in chars)
        self.assertEqual(ac_tester.char_converter(*chars), expected)

    def test_unsigned_char_converter(self):
        from _testcapi import UCHAR_MAX
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(UCHAR_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(0, UCHAR_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_char_converter([])
        self.assertEqual(ac_tester.unsigned_char_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_char_converter(0, 0, UCHAR_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_char_converter(0, 0, (UCHAR_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_short_converter(self):
        from _testcapi import SHRT_MIN, SHRT_MAX
        with self.assertRaises(OverflowError):
            ac_tester.short_converter(SHRT_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.short_converter(SHRT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.short_converter([])
        self.assertEqual(ac_tester.short_converter(-1234), (-1234,))
        self.assertEqual(ac_tester.short_converter(4321), (4321,))

    def test_unsigned_short_converter(self):
        from _testcapi import USHRT_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_short_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_short_converter(USHRT_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_short_converter(0, USHRT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_short_converter([])
        self.assertEqual(ac_tester.unsigned_short_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_short_converter(0, 0, USHRT_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_short_converter(0, 0, (USHRT_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_int_converter(self):
        from _testcapi import INT_MIN, INT_MAX
        with self.assertRaises(OverflowError):
            ac_tester.int_converter(INT_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.int_converter(INT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.int_converter(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.int_converter([])
        self.assertEqual(ac_tester.int_converter(), (12, 34, 45))
        self.assertEqual(ac_tester.int_converter(1, 2, '3'), (1, 2, ord('3')))

    def test_unsigned_int_converter(self):
        from _testcapi import UINT_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_int_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_int_converter(UINT_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_int_converter(0, UINT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_int_converter([])
        self.assertEqual(ac_tester.unsigned_int_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_int_converter(0, 0, UINT_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_int_converter(0, 0, (UINT_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_long_converter(self):
        from _testcapi import LONG_MIN, LONG_MAX
        with self.assertRaises(OverflowError):
            ac_tester.long_converter(LONG_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.long_converter(LONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.long_converter([])
        self.assertEqual(ac_tester.long_converter(), (12,))
        self.assertEqual(ac_tester.long_converter(-1234), (-1234,))

    def test_unsigned_long_converter(self):
        from _testcapi import ULONG_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_long_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_converter(ULONG_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_converter(0, ULONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_long_converter([])
        self.assertEqual(ac_tester.unsigned_long_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_long_converter(0, 0, ULONG_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_long_converter(0, 0, (ULONG_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_long_long_converter(self):
        from _testcapi import LLONG_MIN, LLONG_MAX
        with self.assertRaises(OverflowError):
            ac_tester.long_long_converter(LLONG_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.long_long_converter(LLONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.long_long_converter([])
        self.assertEqual(ac_tester.long_long_converter(), (12,))
        self.assertEqual(ac_tester.long_long_converter(-1234), (-1234,))

    def test_unsigned_long_long_converter(self):
        from _testcapi import ULLONG_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_long_long_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_long_converter(ULLONG_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_long_converter(0, ULLONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_long_long_converter([])
        self.assertEqual(ac_tester.unsigned_long_long_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_long_long_converter(0, 0, ULLONG_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_long_long_converter(0, 0, (ULLONG_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_py_ssize_t_converter(self):
        from _testcapi import PY_SSIZE_T_MIN, PY_SSIZE_T_MAX
        with self.assertRaises(OverflowError):
            ac_tester.py_ssize_t_converter(PY_SSIZE_T_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.py_ssize_t_converter(PY_SSIZE_T_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.py_ssize_t_converter([])
        self.assertEqual(ac_tester.py_ssize_t_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.py_ssize_t_converter(1, 2, None), (1, 2, 56))

    def test_slice_index_converter(self):
        from _testcapi import PY_SSIZE_T_MIN, PY_SSIZE_T_MAX
        with self.assertRaises(TypeError):
            ac_tester.slice_index_converter([])
        self.assertEqual(ac_tester.slice_index_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.slice_index_converter(1, 2, None), (1, 2, 56))
        self.assertEqual(ac_tester.slice_index_converter(PY_SSIZE_T_MAX, PY_SSIZE_T_MAX + 1, PY_SSIZE_T_MAX + 1234),
                         (PY_SSIZE_T_MAX, PY_SSIZE_T_MAX, PY_SSIZE_T_MAX))
        self.assertEqual(ac_tester.slice_index_converter(PY_SSIZE_T_MIN, PY_SSIZE_T_MIN - 1, PY_SSIZE_T_MIN - 1234),
                         (PY_SSIZE_T_MIN, PY_SSIZE_T_MIN, PY_SSIZE_T_MIN))

    def test_size_t_converter(self):
        with self.assertRaises(ValueError):
            ac_tester.size_t_converter(-1)
        with self.assertRaises(TypeError):
            ac_tester.size_t_converter([])
        self.assertEqual(ac_tester.size_t_converter(), (12,))

    def test_float_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.float_converter([])
        self.assertEqual(ac_tester.float_converter(), (12.5,))
        self.assertEqual(ac_tester.float_converter(-0.5), (-0.5,))

    def test_double_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.double_converter([])
        self.assertEqual(ac_tester.double_converter(), (12.5,))
        self.assertEqual(ac_tester.double_converter(-0.5), (-0.5,))

    def test_py_complex_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.py_complex_converter([])
        self.assertEqual(ac_tester.py_complex_converter(complex(1, 2)), (complex(1, 2),))
        self.assertEqual(ac_tester.py_complex_converter(complex('-1-2j')), (complex('-1-2j'),))
        self.assertEqual(ac_tester.py_complex_converter(-0.5), (-0.5,))
        self.assertEqual(ac_tester.py_complex_converter(10), (10,))

    def test_str_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.str_converter(1)
        with self.assertRaises(TypeError):
            ac_tester.str_converter('a', 'b', 'c')
        with self.assertRaises(ValueError):
            ac_tester.str_converter('a', b'b\0b', 'c')
        self.assertEqual(ac_tester.str_converter('a', b'b', 'c'), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter('a', b'b', b'c'), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter('a', b'b', 'c\0c'), ('a', 'b', 'c\0c'))

    def test_str_converter_encoding(self):
        with self.assertRaises(TypeError):
            ac_tester.str_converter_encoding(1)
        self.assertEqual(ac_tester.str_converter_encoding('a', 'b', 'c'), ('a', 'b', 'c'))
        with self.assertRaises(TypeError):
            ac_tester.str_converter_encoding('a', b'b\0b', 'c')
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', bytearray([ord('c')])), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', bytearray([ord('c'), 0, ord('c')])),
                         ('a', 'b', 'c\x00c'))
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', b'c\x00c'), ('a', 'b', 'c\x00c'))

    def test_py_buffer_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.py_buffer_converter('a', 'b')
        self.assertEqual(ac_tester.py_buffer_converter('abc', bytearray([1, 2, 3])), (b'abc', b'\x01\x02\x03'))

    def test_keywords(self):
        self.assertEqual(ac_tester.keywords(1, 2), (1, 2))
        self.assertEqual(ac_tester.keywords(1, b=2), (1, 2))
        self.assertEqual(ac_tester.keywords(a=1, b=2), (1, 2))

    def test_keywords_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.keywords_kwonly(1, 2)
        self.assertEqual(ac_tester.keywords_kwonly(1, b=2), (1, 2))
        self.assertEqual(ac_tester.keywords_kwonly(a=1, b=2), (1, 2))

    def test_keywords_opt(self):
        self.assertEqual(ac_tester.keywords_opt(1), (1, None, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2, 3), (1, 2, 3))
        self.assertEqual(ac_tester.keywords_opt(1, b=2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2, c=3), (1, 2, 3))
        self.assertEqual(ac_tester.keywords_opt(a=1, c=3), (1, None, 3))
        self.assertEqual(ac_tester.keywords_opt(a=1, b=2, c=3), (1, 2, 3))

    def test_keywords_opt_kwonly(self):
        self.assertEqual(ac_tester.keywords_opt_kwonly(1), (1, None, None, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.keywords_opt_kwonly(1, 2, 3)
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(a=1, c=3), (1, None, 3, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(a=1, b=2, c=3, d=4), (1, 2, 3, 4))

    def test_keywords_kwonly_opt(self):
        self.assertEqual(ac_tester.keywords_kwonly_opt(1), (1, None, None))
        with self.assertRaises(TypeError):
            ac_tester.keywords_kwonly_opt(1, 2)
        self.assertEqual(ac_tester.keywords_kwonly_opt(1, b=2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_kwonly_opt(a=1, c=3), (1, None, 3))
        self.assertEqual(ac_tester.keywords_kwonly_opt(a=1, b=2, c=3), (1, 2, 3))

    def test_posonly_keywords(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords(a=1, b=2)
        self.assertEqual(ac_tester.posonly_keywords(1, 2), (1, 2))
        self.assertEqual(ac_tester.posonly_keywords(1, b=2), (1, 2))

    def test_posonly_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(1, 2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(a=1, b=2)
        self.assertEqual(ac_tester.posonly_kwonly(1, b=2), (1, 2))

    def test_posonly_keywords_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(a=1, b=2, c=3)
        self.assertEqual(ac_tester.posonly_keywords_kwonly(1, 2, c=3), (1, 2, 3))
        self.assertEqual(ac_tester.posonly_keywords_kwonly(1, b=2, c=3), (1, 2, 3))

    def test_posonly_keywords_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt(1)
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, 3, 4), (1, 2, 3, 4))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, c=3), (1, 2, 3, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt(a=1, b=2, c=3, d=4)
        self.assertEqual(ac_tester.posonly_keywords_opt(1, b=2, c=3, d=4), (1, 2, 3, 4))

    def test_posonly_opt_keywords_opt(self):
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, 3, 4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt(a=1, b=2, c=3, d=4)

    def test_posonly_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(1, 2)
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(a=1, b=2, c=3, d=4)

    def test_posonly_opt_kwonly_opt(self):
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_kwonly_opt(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_kwonly_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4))

    def test_posonly_keywords_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, 2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, b=2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(a=1, b=2, c=3)
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, b=2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3, d=4, e=5), (1, 2, 3, 4, 5))

    def test_posonly_keywords_opt_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(1)
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2), (1, 2, None, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, b=2), (1, 2, None, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, 4)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(a=1, b=2)
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, b=2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, d=4, e=5), (1, 2, 3, 4, 5))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3, d=4, e=5), (1, 2, 3, 4, 5))

    def test_posonly_opt_keywords_opt_kwonly_opt(self):
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3, d=4), (1, 2, 3, 4))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3, 4)

    def test_keyword_only_parameter(self):
        with self.assertRaises(TypeError):
            ac_tester.keyword_only_parameter()
        with self.assertRaises(TypeError):
            ac_tester.keyword_only_parameter(1)
        self.assertEqual(ac_tester.keyword_only_parameter(a=1), (1,))

    def test_posonly_vararg(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_vararg()
        self.assertEqual(ac_tester.posonly_vararg(1, 2), (1, 2, ()))
        self.assertEqual(ac_tester.posonly_vararg(1, b=2), (1, 2, ()))
        self.assertEqual(ac_tester.posonly_vararg(1, 2, 3, 4), (1, 2, (3, 4)))

    def test_vararg_and_posonly(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg_and_posonly()
        with self.assertRaises(TypeError):
            ac_tester.vararg_and_posonly(1, b=2)
        self.assertEqual(ac_tester.vararg_and_posonly(1, 2, 3, 4), (1, (2, 3, 4)))

    def test_vararg(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg()
        with self.assertRaises(TypeError):
            ac_tester.vararg(1, b=2)
        self.assertEqual(ac_tester.vararg(1, 2, 3, 4), (1, (2, 3, 4)))

    def test_vararg_with_default(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg_with_default()
        self.assertEqual(ac_tester.vararg_with_default(1, b=False), (1, (), False))
        self.assertEqual(ac_tester.vararg_with_default(1, 2, 3, 4), (1, (2, 3, 4), False))
        self.assertEqual(ac_tester.vararg_with_default(1, 2, 3, 4, b=True), (1, (2, 3, 4), True))

    def test_vararg_with_only_defaults(self):
        self.assertEqual(ac_tester.vararg_with_only_defaults(), ((), None))
        self.assertEqual(ac_tester.vararg_with_only_defaults(b=2), ((), 2))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, b=2), ((1, ), 2))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, 2, 3, 4), ((1, 2, 3, 4), None))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, 2, 3, 4, b=5), ((1, 2, 3, 4), 5))

    def test_gh_32092_oob(self):
        ac_tester.gh_32092_oob(1, 2, 3, 4, kw1=5, kw2=6)

    def test_gh_32092_kw_pass(self):
        ac_tester.gh_32092_kw_pass(1, 2, 3)

    def test_gh_99233_refcount(self):
        arg = '*A unique string is not referenced by anywhere else.*'
        arg_refcount_origin = sys.getrefcount(arg)
        ac_tester.gh_99233_refcount(arg)
        arg_refcount_after = sys.getrefcount(arg)
        self.assertEqual(arg_refcount_origin, arg_refcount_after)

    def test_gh_99240_double_free(self):
        err = re.escape(
            "gh_99240_double_free() argument 2 must be encoded string "
            "without null bytes, not str"
        )
        with self.assertRaisesRegex(TypeError, err):
            ac_tester.gh_99240_double_free('a', '\0b')

    def test_cloned_func_exception_message(self):
        incorrect_arg = -1  # f1() and f2() accept a single str
        with self.assertRaisesRegex(TypeError, "clone_f1"):
            ac_tester.clone_f1(incorrect_arg)
        with self.assertRaisesRegex(TypeError, "clone_f2"):
            ac_tester.clone_f2(incorrect_arg)

    def test_cloned_func_with_converter_exception_message(self):
        for name in "clone_with_conv_f1", "clone_with_conv_f2":
            with self.subTest(name=name):
                func = getattr(ac_tester, name)
                self.assertEqual(func(), name)

    def test_depr_star_new(self):
        regex = re.escape(
            "Passing positional arguments to _testclinic.DeprStarNew() is "
            "deprecated. Parameter 'a' will become a keyword-only parameter "
            "in Python 3.14."
        )
        with self.assertWarnsRegex(DeprecationWarning, regex) as cm:
            ac_tester.DeprStarNew(None)
        self.assertEqual(cm.filename, __file__)

    def test_depr_star_init(self):
        regex = re.escape(
            "Passing positional arguments to _testclinic.DeprStarInit() is "
            "deprecated. Parameter 'a' will become a keyword-only parameter "
            "in Python 3.14."
        )
        with self.assertWarnsRegex(DeprecationWarning, regex) as cm:
            ac_tester.DeprStarInit(None)
        self.assertEqual(cm.filename, __file__)

    def test_depr_star_pos0_len1(self):
        fn = ac_tester.depr_star_pos0_len1
        fn(a=None)
        self.check_depr_star("'a'", fn, "a")

    def test_depr_star_pos0_len2(self):
        fn = ac_tester.depr_star_pos0_len2
        fn(a=0, b=0)
        check = partial(self.check_depr_star, "'a' and 'b'", fn)
        check("a", b=0)
        check("a", "b")

    def test_depr_star_pos0_len3_with_kwd(self):
        fn = ac_tester.depr_star_pos0_len3_with_kwd
        fn(a=0, b=0, c=0, d=0)
        check = partial(self.check_depr_star, "'a', 'b' and 'c'", fn)
        check("a", b=0, c=0, d=0)
        check("a", "b", c=0, d=0)
        check("a", "b", "c", d=0)

    def test_depr_star_pos1_len1_opt(self):
        fn = ac_tester.depr_star_pos1_len1_opt
        fn(a=0, b=0)
        fn("a", b=0)
        fn(a=0)  # b is optional
        check = partial(self.check_depr_star, "'b'", fn)
        check("a", "b")

    def test_depr_star_pos1_len1(self):
        fn = ac_tester.depr_star_pos1_len1
        fn(a=0, b=0)
        fn("a", b=0)
        check = partial(self.check_depr_star, "'b'", fn)
        check("a", "b")

    def test_depr_star_pos1_len2_with_kwd(self):
        fn = ac_tester.depr_star_pos1_len2_with_kwd
        fn(a=0, b=0, c=0, d=0),
        fn("a", b=0, c=0, d=0),
        check = partial(self.check_depr_star, "'b' and 'c'", fn)
        check("a", "b", c=0, d=0),
        check("a", "b", "c", d=0),

    def test_depr_star_pos2_len1(self):
        fn = ac_tester.depr_star_pos2_len1
        fn(a=0, b=0, c=0)
        fn("a", b=0, c=0)
        fn("a", "b", c=0)
        check = partial(self.check_depr_star, "'c'", fn)
        check("a", "b", "c")

    def test_depr_star_pos2_len2(self):
        fn = ac_tester.depr_star_pos2_len2
        fn(a=0, b=0, c=0, d=0)
        fn("a", b=0, c=0, d=0)
        fn("a", "b", c=0, d=0)
        check = partial(self.check_depr_star, "'c' and 'd'", fn)
        check("a", "b", "c", d=0)
        check("a", "b", "c", "d")

    def test_depr_star_pos2_len2_with_kwd(self):
        fn = ac_tester.depr_star_pos2_len2_with_kwd
        fn(a=0, b=0, c=0, d=0, e=0)
        fn("a", b=0, c=0, d=0, e=0)
        fn("a", "b", c=0, d=0, e=0)
        check = partial(self.check_depr_star, "'c' and 'd'", fn)
        check("a", "b", "c", d=0, e=0)
        check("a", "b", "c", "d", e=0)


class PermutationTests(unittest.TestCase):
    """Test permutation support functions."""

    def test_permute_left_option_groups(self):
        expected = (
            (),
            (3,),
            (2, 3),
            (1, 2, 3),
        )
        data = list(zip([1, 2, 3]))  # Generate a list of 1-tuples.
        actual = tuple(clinic.permute_left_option_groups(data))
        self.assertEqual(actual, expected)

    def test_permute_right_option_groups(self):
        expected = (
            (),
            (1,),
            (1, 2),
            (1, 2, 3),
        )
        data = list(zip([1, 2, 3]))  # Generate a list of 1-tuples.
        actual = tuple(clinic.permute_right_option_groups(data))
        self.assertEqual(actual, expected)

    def test_permute_optional_groups(self):
        empty = {
            "left": (), "required": (), "right": (),
            "expected": ((),),
        }
        noleft1 = {
            "left": (), "required": ("b",), "right": ("c",),
            "expected": (
                ("b",),
                ("b", "c"),
            ),
        }
        noleft2 = {
            "left": (), "required": ("b", "c",), "right": ("d",),
            "expected": (
                ("b", "c"),
                ("b", "c", "d"),
            ),
        }
        noleft3 = {
            "left": (), "required": ("b", "c",), "right": ("d", "e"),
            "expected": (
                ("b", "c"),
                ("b", "c", "d"),
                ("b", "c", "d", "e"),
            ),
        }
        noright1 = {
            "left": ("a",), "required": ("b",), "right": (),
            "expected": (
                ("b",),
                ("a", "b"),
            ),
        }
        noright2 = {
            "left": ("a",), "required": ("b", "c"), "right": (),
            "expected": (
                ("b", "c"),
                ("a", "b", "c"),
            ),
        }
        noright3 = {
            "left": ("a", "b"), "required": ("c",), "right": (),
            "expected": (
                ("c",),
                ("b", "c"),
                ("a", "b", "c"),
            ),
        }
        leftandright1 = {
            "left": ("a",), "required": ("b",), "right": ("c",),
            "expected": (
                ("b",),
                ("a", "b"),  # Prefer left.
                ("a", "b", "c"),
            ),
        }
        leftandright2 = {
            "left": ("a", "b"), "required": ("c", "d"), "right": ("e", "f"),
            "expected": (
                ("c", "d"),
                ("b", "c", "d"),       # Prefer left.
                ("a", "b", "c", "d"),  # Prefer left.
                ("a", "b", "c", "d", "e"),
                ("a", "b", "c", "d", "e", "f"),
            ),
        }
        dataset = (
            empty,
            noleft1, noleft2, noleft3,
            noright1, noright2, noright3,
            leftandright1, leftandright2,
        )
        for params in dataset:
            with self.subTest(**params):
                left, required, right, expected = params.values()
                permutations = clinic.permute_optional_groups(left, required, right)
                actual = tuple(permutations)
                self.assertEqual(actual, expected)


class FormatHelperTests(unittest.TestCase):

    def test_strip_leading_and_trailing_blank_lines(self):
        dataset = (
            # Input lines, expected output.
            ("a\nb",            "a\nb"),
            ("a\nb\n",          "a\nb"),
            ("a\nb ",           "a\nb"),
            ("\na\nb\n\n",      "a\nb"),
            ("\n\na\nb\n\n",    "a\nb"),
            ("\n\na\n\nb\n\n",  "a\n\nb"),
            # Note, leading whitespace is preserved:
            (" a\nb",               " a\nb"),
            (" a\nb ",              " a\nb"),
            (" \n \n a\nb \n \n ",  " a\nb"),
        )
        for lines, expected in dataset:
            with self.subTest(lines=lines, expected=expected):
                out = clinic.strip_leading_and_trailing_blank_lines(lines)
                self.assertEqual(out, expected)

    def test_normalize_snippet(self):
        snippet = """
            one
            two
            three
        """

        # Expected outputs:
        zero_indent = (
            "one\n"
            "two\n"
            "three"
        )
        four_indent = (
            "    one\n"
            "    two\n"
            "    three"
        )
        eight_indent = (
            "        one\n"
            "        two\n"
            "        three"
        )
        expected_outputs = {0: zero_indent, 4: four_indent, 8: eight_indent}
        for indent, expected in expected_outputs.items():
            with self.subTest(indent=indent):
                actual = clinic.normalize_snippet(snippet, indent=indent)
                self.assertEqual(actual, expected)

    def test_accumulator(self):
        acc = clinic.text_accumulator()
        self.assertEqual(acc.output(), "")
        acc.append("a")
        self.assertEqual(acc.output(), "a")
        self.assertEqual(acc.output(), "")
        acc.append("b")
        self.assertEqual(acc.output(), "b")
        self.assertEqual(acc.output(), "")
        acc.append("c")
        acc.append("d")
        self.assertEqual(acc.output(), "cd")
        self.assertEqual(acc.output(), "")

    def test_quoted_for_c_string(self):
        dataset = (
            # input,    expected
            (r"abc",    r"abc"),
            (r"\abc",   r"\\abc"),
            (r"\a\bc",  r"\\a\\bc"),
            (r"\a\\bc", r"\\a\\\\bc"),
            (r'"abc"',  r'\"abc\"'),
            (r"'a'",    r"\'a\'"),
        )
        for line, expected in dataset:
            with self.subTest(line=line, expected=expected):
                out = clinic.quoted_for_c_string(line)
                self.assertEqual(out, expected)

    def test_rstrip_lines(self):
        lines = (
            "a \n"
            "b\n"
            " c\n"
            " d \n"
        )
        expected = (
            "a\n"
            "b\n"
            " c\n"
            " d\n"
        )
        out = clinic.rstrip_lines(lines)
        self.assertEqual(out, expected)

    def test_format_escape(self):
        line = "{}, {a}"
        expected = "{{}}, {{a}}"
        out = clinic.format_escape(line)
        self.assertEqual(out, expected)

    def test_indent_all_lines(self):
        # Blank lines are expected to be unchanged.
        self.assertEqual(clinic.indent_all_lines("", prefix="bar"), "")

        lines = (
            "one\n"
            "two"  # The missing newline is deliberate.
        )
        expected = (
            "barone\n"
            "bartwo"
        )
        out = clinic.indent_all_lines(lines, prefix="bar")
        self.assertEqual(out, expected)

        # If last line is empty, expect it to be unchanged.
        lines = (
            "\n"
            "one\n"
            "two\n"
            ""
        )
        expected = (
            "bar\n"
            "barone\n"
            "bartwo\n"
            ""
        )
        out = clinic.indent_all_lines(lines, prefix="bar")
        self.assertEqual(out, expected)

    def test_suffix_all_lines(self):
        # Blank lines are expected to be unchanged.
        self.assertEqual(clinic.suffix_all_lines("", suffix="foo"), "")

        lines = (
            "one\n"
            "two"  # The missing newline is deliberate.
        )
        expected = (
            "onefoo\n"
            "twofoo"
        )
        out = clinic.suffix_all_lines(lines, suffix="foo")
        self.assertEqual(out, expected)

        # If last line is empty, expect it to be unchanged.
        lines = (
            "\n"
            "one\n"
            "two\n"
            ""
        )
        expected = (
            "foo\n"
            "onefoo\n"
            "twofoo\n"
            ""
        )
        out = clinic.suffix_all_lines(lines, suffix="foo")
        self.assertEqual(out, expected)


class ClinicReprTests(unittest.TestCase):
    def test_Block_repr(self):
        block = clinic.Block("foo")
        expected_repr = "<clinic.Block 'text' input='foo' output=None>"
        self.assertEqual(repr(block), expected_repr)

        block2 = clinic.Block("bar", "baz", [], "eggs", "spam")
        expected_repr_2 = "<clinic.Block 'baz' input='bar' output='eggs'>"
        self.assertEqual(repr(block2), expected_repr_2)

        block3 = clinic.Block(
            input="longboi_" * 100,
            dsl_name="wow_so_long",
            signatures=[],
            output="very_long_" * 100,
            indent=""
        )
        expected_repr_3 = (
            "<clinic.Block 'wow_so_long' input='longboi_longboi_longboi_l...' output='very_long_very_long_very_...'>"
        )
        self.assertEqual(repr(block3), expected_repr_3)

    def test_Destination_repr(self):
        c = _make_clinic()

        destination = clinic.Destination(
            "foo", type="file", clinic=c, args=("eggs",)
        )
        self.assertEqual(
            repr(destination), "<clinic.Destination 'foo' type='file' file='eggs'>"
        )

        destination2 = clinic.Destination("bar", type="buffer", clinic=c)
        self.assertEqual(repr(destination2), "<clinic.Destination 'bar' type='buffer'>")

    def test_Module_repr(self):
        module = clinic.Module("foo", _make_clinic())
        self.assertRegex(repr(module), r"<clinic.Module 'foo' at \d+>")

    def test_Class_repr(self):
        cls = clinic.Class("foo", _make_clinic(), None, 'some_typedef', 'some_type_object')
        self.assertRegex(repr(cls), r"<clinic.Class 'foo' at \d+>")

    def test_FunctionKind_repr(self):
        self.assertEqual(
            repr(clinic.FunctionKind.INVALID), "<clinic.FunctionKind.INVALID>"
        )
        self.assertEqual(
            repr(clinic.FunctionKind.CLASS_METHOD), "<clinic.FunctionKind.CLASS_METHOD>"
        )

    def test_Function_and_Parameter_reprs(self):
        function = clinic.Function(
            name='foo',
            module=_make_clinic(),
            cls=None,
            c_basename=None,
            full_name='foofoo',
            return_converter=clinic.init_return_converter(),
            kind=clinic.FunctionKind.METHOD_INIT,
            coexist=False
        )
        self.assertEqual(repr(function), "<clinic.Function 'foo'>")

        converter = clinic.self_converter('bar', 'bar', function)
        parameter = clinic.Parameter(
            "bar",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            function=function,
            converter=converter
        )
        self.assertEqual(repr(parameter), "<clinic.Parameter 'bar'>")

    def test_Monitor_repr(self):
        monitor = clinic.cpp.Monitor()
        self.assertRegex(repr(monitor), r"<clinic.Monitor \d+ line=0 condition=''>")

        monitor.line_number = 42
        monitor.stack.append(("token1", "condition1"))
        self.assertRegex(
            repr(monitor), r"<clinic.Monitor \d+ line=42 condition='condition1'>"
        )

        monitor.stack.append(("token2", "condition2"))
        self.assertRegex(
            repr(monitor),
            r"<clinic.Monitor \d+ line=42 condition='condition1 && condition2'>"
        )


if __name__ == "__main__":
    unittest.main()
