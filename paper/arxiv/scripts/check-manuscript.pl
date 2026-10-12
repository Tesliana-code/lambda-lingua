#!/usr/bin/env perl
use strict;
use warnings;
use utf8;

my $texfile = 'paper/arxiv/main.tex';
open my $fh, '<:encoding(UTF-8)', $texfile or die "Unable to read $texfile: $!\n";
my $tex = do { local $/; <$fh> };
close $fh;

die "Missing documentclass\n" unless $tex =~ /\\documentclass(?:\[[^\]]*\])?\{[^}]+\}/;
my @stack;
while ($tex =~ /\\(begin|end)\{([A-Za-z*]+)\}/g) {
    my ($kind, $env) = ($1, $2);
    if ($kind eq 'begin') {
        push @stack, $env;
    } else {
        my $opened = pop @stack;
        die "Mismatched environment: end($env), open(" . ($opened // 'none') . ")\n"
            unless defined($opened) && $opened eq $env;
    }
}
die "Unclosed environment(s): @stack\n" if @stack;
die "Document end marker not found\n" unless $tex =~ /\\end\{document\}/;

my $sources = 0;
my $citations = 0;
my %bib_keys;
for my $bibliography ($tex =~ /\\bibliography\{([^}]+)\}/g) {
    for my $source (split /,/, $bibliography) {
        $source =~ s/^\s+|\s+$//g;
        die "Invalid bibliography name: $source\n"
            unless $source =~ /\A[A-Za-z0-9_.-]+\z/;
        my $path = "paper/arxiv/$source.bib";
        open my $bib, '<:encoding(UTF-8)', $path
            or die "Missing bibliography: $path\n";
        while (my $line = <$bib>) {
            next if $line =~ /^\s*%/;
            $bib_keys{$1} = 1 if $line =~ /^\s*\@\w+\s*\{\s*([^,\s}]+)/;
        }
        close $bib;
        $sources++;
    }
}
for my $cite ($tex =~ /\\cite(?:\[[^\]]*\])?\{([^}]+)\}/g) {
    for my $key (split /,/, $cite) {
        $key =~ s/^\s+|\s+$//g;
        die "Missing bibliography key: $key\n" unless exists $bib_keys{$key};
        $citations++;
    }
}
for my $input ($tex =~ /\\(?:input|include)\{([^}]+)\}/g) {
    die "Unsafe input path: $input\n"
        unless $input =~ /\A[A-Za-z0-9_./-]+\z/ && $input !~ m{(?:^|/)\.\.(?:/|$)};
    my $path = "paper/arxiv/$input";
    die "Missing input: $path\n" unless -f $path || -f "$path.tex";
}
print "Manuscript structure PASS: balanced environments, $sources bibliography source(s), $citations citation(s)\n";
