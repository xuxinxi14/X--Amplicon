# Linux tool binaries

Place the redistributable Linux tool binaries here:

```text
bin/usearch
bin/vsearch
```

Then prepare executable permissions and run setup:

```bash
chmod +x bin/usearch bin/vsearch
./setup_linux.sh
```

Check the binaries before running a full pipeline:

```bash
./bin/usearch --version
./bin/vsearch --version
```

Known tested versions in the Linux server package:

```text
usearch v10.0.240_i86linux32
vsearch v2.15.2_linux_x86_64
```

`vsearch` should normally be a native x86_64 Linux binary. Some licensed
USEARCH Linux builds report `i86linux32`; they can still run on compatible
x86_64 Linux systems, but should be tested on the target server. Confirm the
USEARCH license and redistribution terms before including it in a public or
shared Linux package.
