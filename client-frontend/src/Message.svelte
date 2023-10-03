<script>
 import { onMount } from "svelte";
 import { persona, read_messages } from "./store";

 export let sender;
 export let timestamp;
 export let message;
 export let nonce;
 export let receive_time = null;

 const date = new Date((receive_time | timestamp) * 1000);

 function markRead() {
     if (!(nonce in $read_messages)) {
         $read_messages = {...$read_messages, [nonce]: 1};
     }
 }

 onMount(markRead);
</script>

<li class="{sender === persona ? 'self' : 'other'}">
    <p>{message}</p>
    <time>{date.toLocaleString()}</time>
</li>

<style>

 li {
     flex: none;
     min-height: 0;
     max-width: 90%;

     display: flex;
     flex-direction: column;
 }

 li.self {
     align-self: flex-end;
     align-items: flex-end;
 }

 li.other {
     align-self: flex-start;
     align-items: flex-start;
 }

 p {
     background: rgb(20, 130, 120);
     font-size: 1.2em;
     color: white;
     padding: 0.4em;
     margin: 0;
     border-radius: 0.5em;
 }

 time {
     font-size: 0.9em;
 }

</style>
