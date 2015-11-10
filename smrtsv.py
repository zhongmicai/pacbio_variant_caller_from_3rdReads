import argparse
import subprocess
import sys

CLUSTER_SETTINGS = '" -q all.q -V -cwd -e ./log -o ./log {params.sge_opts} -w n -S /bin/bash"'
CLUSTER_FLAG = ("--drmaa", CLUSTER_SETTINGS, "-w", "30")

def _build_prefix(args):
    prefix = ["snakemake", "-pq", "-j", str(args.jobs)]
    if args.distribute:
        prefix.extend(CLUSTER_FLAG)

    return tuple(prefix)

def index(args):
    prefix = _build_prefix(args)
    command = prefix + ("prepare_reference", "--config", "reference=%s" % args.reference)
    return subprocess.call(" ".join(command), shell=True)

def align(args):
    prefix = _build_prefix(args)
    command = prefix + (
        "align_reads",
        "--config",
        "reference=%s" % args.reference,
        "reads=%s" % args.reads,
        "alignments=%s" % args.alignments,
        "alignments_dir=%s" % args.alignments_dir,
        "batches=%s" % args.batches,
        "threads=%s" % args.threads
    )
    return subprocess.call(" ".join(command), shell=True)

def call(args):
    # Find candidate regions in alignments.
    sys.stdout.write("Searching for candidate regions\n")
    prefix = _build_prefix(args)
    command = prefix + (
        "get_regions",
        "--config",
        "reference=%s" % args.reference,
        "alignments=%s" % args.alignments,
        "regions_to_exclude=%s" % args.exclude
    )
    return_code = subprocess.call(" ".join(command), shell=True)

    if return_code != 0:
        sys.stderr.write("Failed to identify candidate regions\n")
        return return_code

    # Generate local assemblies across the genome.
    sys.stdout.write("Starting local assemblies\n")
    command = prefix + (
        "collect_assembly_alignments",
        "--config",
        "reference=%s" % args.reference,
        "alignments=%s" % args.alignments
    )
    return_code = subprocess.call(" ".join(command), shell=True)

    if return_code != 0:
        sys.stderr.write("Failed to generate local assemblies\n")
        return return_code

    # Call SVs, indels, and inversions.
    sys.stdout.write("Calling variants\n")
    command = prefix + (
        "call_variants",
        "--config",
        "reference=%s" % args.reference
    )
    return_code = subprocess.call(" ".join(command), shell=True)

    if return_code != 0:
        sys.stderr.write("Failed to call variants\n")
        return return_code

def genotype(args):
    print("Genotype")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribute", action="store_true", help="Distribute analysis to Grid Engine-style cluster")
    parser.add_argument("--jobs", help="number of jobs to run simultaneously", type=int, default=1)
    subparsers = parser.add_subparsers()

    # Index a reference for use by BLASR.
    parser_index = subparsers.add_parser("index", help="index a reference sequence for use by BLASR")
    parser_index.add_argument("reference", help="FASTA file of reference to index")
    parser_index.set_defaults(func=index)

    # Align PacBio reads to an indexed reference with BLASR.
    parser_align = subparsers.add_parser("align", help="align PacBio reads to an indexed reference with BLASR")
    parser_align.add_argument("reference", help="FASTA file of indexed reference with .ctab and .sa in the same directory")
    parser_align.add_argument("reads", help="text file with one absolute path to a PacBio reads file (.bax.h5) per line")
    parser_align.add_argument("--alignments", help="text file with one absolute path to a BLASR alignments file (.bam) per line", default="alignments.fofn")
    parser_align.add_argument("--alignments_dir", help="absolute path of directory for BLASR alignment files", default="alignments")
    parser_align.add_argument("--batches", help="number of batches to split input reads into such that there will be one BAM output file per batch", type=int, default=1)
    parser_align.add_argument("--threads", help="number of threads to use for each BLASR alignment job", type=int, default=1)
    parser_align.set_defaults(func=align)

    # Call SVs and indels from BLASR alignments.
    parser_caller = subparsers.add_parser("call", help="call SVs and indels by local assembly of BLASR-aligned reads")
    parser_caller.add_argument("reference", help="FASTA file of indexed reference with .ctab and .sa in the same directory")
    parser_caller.add_argument("alignments", help="text file with one absolute path to a BLASR alignments file (.bam) per line")
    parser_caller.add_argument("variants", help="VCF of variants called by local assembly alignments")
    parser_caller.add_argument("--exclude", help="BED file of regions to exclude from local assembly (e.g., heterochromatic sequences, etc.)")
    parser_caller.set_defaults(func=call)

    # Genotype SVs with Illumina reads.
    parser_genotyper = subparsers.add_parser("genotype", help="Genotype SVs with Illumina reads")
    parser_genotyper.add_argument("variants", help="VCF of SMRT SV variants to genotype")
    parser_genotyper.add_argument("genotyped_variants", help="VCF of SMRT SV variant genotypes for the given sample-level BAMs")
    parser_genotyper.add_argument("samples", nargs="+", help="one or more sample-level BAMs to genotype for the given variants")
    parser_genotyper.set_defaults(func=genotype)

    args = parser.parse_args()
    return_code = args.func(args)
    sys.exit(return_code)
