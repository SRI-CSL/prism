# PRISM Client Web Frontend

This directory contains the sources for Javascript-based frontend for our client. The frontend is a [Svelte](https://svelte.dev/) app which gets compiled to `index.html`, `assets/index.[hash].js`, and `assets/index.[hash].css`, which are packaged with and served by the `prism.client.web` Python module.

## Development

For development, you will need `node` version 12.0 or greater and `npm` installed. If you have Nix handy, `nix-shell` will drop you into a development shell with those packages installed. Then,

``` bash
npm install
```

to fetch the dependencies specified in `package.json`, and

``` bash
npm run dev
```

to run a development server at [http://localhost:5000/](http://localhost:5000/). The development server will proxy requests to `prism-client-00001` running in the local prism testbed, which can be started with `prism test -b --no-test` (see [main README](../README.md) for details about `prism` command).

## Production

Once you're satisfied with your changes, run

``` bash
npm run build
```

which will create a minified production build for the `prism.client.web` module.
