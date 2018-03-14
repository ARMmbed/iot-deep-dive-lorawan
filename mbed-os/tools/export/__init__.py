"""The generic interface for all exporters.
"""
# mbed SDK
# Copyright (c) 2011-2016 ARM Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function, division, absolute_import

import sys
from os.path import join, abspath, dirname, exists
from os.path import basename, relpath, normpath, splitext
from os import makedirs, walk
import copy
from shutil import rmtree, copyfile
import zipfile

from ..build_api import prepare_toolchain, scan_resources
from ..toolchains import Resources
from ..targets import TARGET_NAMES
from . import (lpcxpresso, ds5_5, iar, makefile, embitz, coide, kds, simplicity,
               atmelstudio, mcuxpresso, sw4stm32, e2studio, zip, cmsis, uvision,
               cdt, vscode, gnuarmeclipse, qtcreator, cmake, nb, cces)

EXPORTERS = {
    u'uvision5': uvision.Uvision,
    u'uvision': uvision.Uvision,
    u'lpcxpresso': lpcxpresso.LPCXpresso,
    u'gcc_arm': makefile.GccArm,
    u'make_gcc_arm': makefile.GccArm,
    u'make_armc5': makefile.Armc5,
    u'make_armc6': makefile.Armc6,
    u'make_iar': makefile.IAR,
    u'ds5_5': ds5_5.DS5_5,
    u'iar': iar.IAR,
    u'embitz' : embitz.EmBitz,
    u'coide' : coide.CoIDE,
    u'kds' : kds.KDS,
    u'simplicityv3' : simplicity.SimplicityV3,
    u'atmelstudio' : atmelstudio.AtmelStudio,
    u'sw4stm32'    : sw4stm32.Sw4STM32,
    u'e2studio' : e2studio.E2Studio,
    u'eclipse_gcc_arm'  : cdt.EclipseGcc,
    u'eclipse_iar'      : cdt.EclipseIAR,
    u'eclipse_armc5'    : cdt.EclipseArmc5,
    u'gnuarmeclipse': gnuarmeclipse.GNUARMEclipse,
    u'mcuxpresso': mcuxpresso.MCUXpresso,
    u'netbeans':     nb.GNUARMNetbeans,
    u'qtcreator': qtcreator.QtCreator,
    u'vscode_gcc_arm' : vscode.VSCodeGcc,
    u'vscode_iar' : vscode.VSCodeIAR,
    u'vscode_armc5' : vscode.VSCodeArmc5,
    u'cmake_gcc_arm': cmake.GccArm,
    u'cces' : cces.CCES
}

ERROR_MESSAGE_UNSUPPORTED_TOOLCHAIN = """
Sorry, the target %s is not currently supported on the %s toolchain.
Please refer to <a href='/handbook/Exporting-to-offline-toolchains' target='_blank'>Exporting to offline toolchains</a> for more information.
"""

ERROR_MESSAGE_NOT_EXPORT_LIBS = """
To export this project please <a href='http://mbed.org/compiler/?import=http://mbed.org/users/mbed_official/code/mbed-export/k&mode=lib' target='_blank'>import the export version of the mbed library</a>.
"""

def mcu_ide_list():
    """Shows list of exportable ides 

    """
    supported_ides = sorted(EXPORTERS.keys())
    return "\n".join(supported_ides)


def mcu_ide_matrix(verbose_html=False):
    """Shows target map using prettytable

    Keyword argumets:
    verbose_html - print the matrix in html format
    """
    supported_ides = sorted(EXPORTERS.keys())
    # Only use it in this function so building works without extra modules
    from prettytable import PrettyTable, ALL

    # All tests status table print
    table_printer = PrettyTable(["Platform"] + supported_ides)
    # Align table
    for col in supported_ides:
        table_printer.align[col] = "c"
    table_printer.align["Platform"] = "l"

    perm_counter = 0
    for target in sorted(TARGET_NAMES):
        row = [target]  # First column is platform name
        for ide in supported_ides:
            text = "-"
            if EXPORTERS[ide].is_target_supported(target):
                if verbose_html:
                    text = "&#10003;"
                else:
                    text = "x"
                perm_counter += 1
            row.append(text)
        table_printer.add_row(row)

    table_printer.border = True
    table_printer.vrules = ALL
    table_printer.hrules = ALL
    # creates a html page in a shorter format suitable for readme.md
    if verbose_html:
        result = table_printer.get_html_string()
    else:
        result = table_printer.get_string()
    result += "\n"
    result += "Total IDEs: %d\n"% (len(supported_ides))
    if verbose_html:
        result += "<br>"
    result += "Total platforms: %d\n"% (len(TARGET_NAMES))
    if verbose_html:
        result += "<br>"
    result += "Total permutations: %d"% (perm_counter)
    if verbose_html:
        result = result.replace("&amp;", "&")
    return result


def get_exporter_toolchain(ide):
    """ Return the exporter class and the toolchain string as a tuple

    Positional arguments:
    ide - the ide name of an exporter
    """
    return EXPORTERS[ide], EXPORTERS[ide].TOOLCHAIN


def rewrite_basepath(file_name, resources, export_path, loc):
    """ Replace the basepath of filename with export_path

    Positional arguments:
    file_name - the absolute path to a file
    resources - the resources object that the file came from
    export_path - the final destination of the file after export
    """
    new_f = join(loc, relpath(file_name, resources.file_basepath[file_name]))
    resources.file_basepath[new_f] = export_path
    return new_f


def subtract_basepath(resources, export_path, loc=""):
    """ Rewrite all of the basepaths with the export_path

    Positional arguments:
    resources - the resource object to rewrite the basepaths of
    export_path - the final destination of the resources with respect to the
      generated project files
    """
    keys = ['s_sources', 'c_sources', 'cpp_sources', 'hex_files',
            'objects', 'libraries', 'inc_dirs', 'headers', 'linker_script',
            'lib_dirs']
    for key in keys:
        vals = getattr(resources, key)
        if isinstance(vals, set):
            vals = list(vals)
        if isinstance(vals, list):
            new_vals = []
            for val in vals:
                new_vals.append(rewrite_basepath(val, resources, export_path,
                                                 loc))
            if isinstance(getattr(resources, key), set):
                setattr(resources, key, set(new_vals))
            else:
                setattr(resources, key, new_vals)
        elif vals:
            setattr(resources, key, rewrite_basepath(vals, resources,
                                                     export_path, loc))


def generate_project_files(resources, export_path, target, name, toolchain, ide,
                           macros=None):
    """Generate the project files for a project

    Positional arguments:
    resources - a Resources object containing all of the files needed to build
      this project
    export_path - location to place project files
    name - name of the project
    toolchain - a toolchain class that corresponds to the toolchain used by the
      IDE or makefile
    ide - IDE name to export to

    Optional arguments:
    macros - additional macros that should be defined within the exported
      project
    """
    exporter_cls, _ = get_exporter_toolchain(ide)
    exporter = exporter_cls(target, export_path, name, toolchain,
                            extra_symbols=macros, resources=resources)
    exporter.generate()
    files = exporter.generated_files
    return files, exporter


def zip_export(file_name, prefix, resources, project_files, inc_repos):
    """Create a zip file from an exported project.

    Positional Parameters:
    file_name - the file name of the resulting zip file
    prefix - a directory name that will prefix the entire zip file's contents
    resources - a resources object with files that must be included in the zip
    project_files - a list of extra files to be added to the root of the prefix
      directory
    """
    with zipfile.ZipFile(file_name, "w") as zip_file:
        for prj_file in project_files:
            zip_file.write(prj_file, join(prefix, basename(prj_file)))
        for loc, res in resources.items():
            to_zip = (
                res.headers + res.s_sources + res.c_sources +\
                res.cpp_sources + res.libraries + res.hex_files + \
                [res.linker_script] + res.bin_files + res.objects + \
                res.json_files + res.lib_refs + res.lib_builds)
            if inc_repos:
                for directory in res.repo_dirs:
                    for root, _, files in walk(directory):
                        for repo_file in files:
                            source = join(root, repo_file)
                            to_zip.append(source)
                            res.file_basepath[source] = res.base_path
                to_zip += res.repo_files
            for source in to_zip:
                if source:
                    zip_file.write(
                        source,
                        join(prefix, loc,
                             relpath(source, res.file_basepath[source])))
            for source in res.lib_builds:
                target_dir, _ = splitext(source)
                dest = join(prefix, loc,
                            relpath(target_dir, res.file_basepath[source]),
                            ".bld", "bldrc")
                zip_file.write(source, dest)



def export_project(src_paths, export_path, target, ide, libraries_paths=None,
                   linker_script=None, notify=None, verbose=False, name=None,
                   inc_dirs=None, jobs=1, silent=False, extra_verbose=False,
                   config=None, macros=None, zip_proj=None, inc_repos=False,
                   build_profile=None, app_config=None):
    """Generates a project file and creates a zip archive if specified

    Positional Arguments:
    src_paths - a list of paths from which to find source files
    export_path - a path specifying the location of generated project files
    target - the mbed board/mcu for which to generate the executable
    ide - the ide for which to generate the project fields

    Keyword Arguments:
    libraries_paths - paths to additional libraries
    linker_script - path to the linker script for the specified target
    notify - function is passed all events, and expected to handle notification
      of the user, emit the events to a log, etc.
    verbose - assigns the notify function to toolchains print_notify_verbose
    name - project name
    inc_dirs - additional include directories
    jobs - number of threads
    silent - silent build - no output
    extra_verbose - assigns the notify function to toolchains
      print_notify_verbose
    config - toolchain's config object
    macros - User-defined macros
    zip_proj - string name of the zip archive you wish to creat (exclude arg
     if you do not wish to create an archive
    """

    # Convert src_path to a list if needed
    if isinstance(src_paths, dict):
        paths = sum(src_paths.values(), [])
    elif isinstance(src_paths, list):
        paths = src_paths[:]
    else:
        paths = [src_paths]

    # Extend src_paths wit libraries_paths
    if libraries_paths is not None:
        paths.extend(libraries_paths)

    if not isinstance(src_paths, dict):
        src_paths = {"": paths}

    # Export Directory
    if not exists(export_path):
        makedirs(export_path)

    _, toolchain_name = get_exporter_toolchain(ide)

    # Pass all params to the unified prepare_resources()
    toolchain = prepare_toolchain(
        paths, "", target, toolchain_name, macros=macros, jobs=jobs,
        notify=notify, silent=silent, verbose=verbose,
        extra_verbose=extra_verbose, config=config, build_profile=build_profile,
        app_config=app_config)
    # The first path will give the name to the library
    toolchain.RESPONSE_FILES = False
    if name is None:
        name = basename(normpath(abspath(src_paths[0])))

    # Call unified scan_resources
    resource_dict = {loc: scan_resources(path, toolchain, inc_dirs=inc_dirs, collect_ignores=True)
                     for loc, path in src_paths.items()}
    resources = Resources()
    toolchain.build_dir = export_path
    config_header = toolchain.get_config_header()
    resources.headers.append(config_header)
    resources.file_basepath[config_header] = dirname(config_header)

    if zip_proj:
        subtract_basepath(resources, ".")
        for loc, res in resource_dict.items():
            temp = copy.deepcopy(res)
            subtract_basepath(temp, ".", loc)
            resources.add(temp)
    else:
        for _, res in resource_dict.items():
            resources.add(res)

    # Change linker script if specified
    if linker_script is not None:
        resources.linker_script = linker_script

    files, exporter = generate_project_files(resources, export_path,
                                             target, name, toolchain, ide,
                                             macros=macros)
    files.append(config_header)
    if zip_proj:
        for resource in resource_dict.values():
            for label, res in resource.features.items():
                if label not in toolchain.target.features:
                    resource.add(res)
        if isinstance(zip_proj, basestring):
            zip_export(join(export_path, zip_proj), name, resource_dict,
                       files + list(exporter.static_files), inc_repos)
        else:
            zip_export(zip_proj, name, resource_dict,
                       files + list(exporter.static_files), inc_repos)
    else:
        for static_file in exporter.static_files:
            if not exists(join(export_path, basename(static_file))):
                copyfile(static_file, join(export_path, basename(static_file)))

    return exporter
