<script>
 import { link } from "svelte-routing";
 import { persona, registerContact } from "./store"
 import Contacts from "./Contacts.svelte"
</script>

<nav>
    <h1>PRISM</h1>
    <h2>Logged in as <span class="nobreak">{persona}</span></h2>
    <hr />
    <Contacts />
    <a href="/" use:link>Help</a>
</nav>

<style>
 nav {
     display: flex;
     flex-direction: column;
     background-color: rgb(25, 128, 119);
     color: white;
     min-width: 200px;
     max-width: 280px;
     padding: 0.5em;
 }

 hr {
     border-top: 1px dashed white;
     width: 90%;
 }

 h1 {
     margin: 0.2em;
     align-self: center;
 }

 h2 {
     font-size: 1em;
     align-self: center;
     word-break: keep-all;
     margin: 0;
     text-align: center;
 }

 a {
     color: white;
     align-self: flex-end;
     flex-grow: 0;
 }

</style>
