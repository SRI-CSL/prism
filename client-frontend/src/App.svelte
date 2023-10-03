<script>
 import { Router, Route } from "svelte-routing";
 import Sidebar from "./Sidebar.svelte"
 import Conversation from "./Conversation.svelte"
</script>

<Router>
    <Sidebar/>
    <main>
        <Route path="/conversations/:contact" let:params>
            {#key params.contact}
                <Conversation contact={params.contact} />
            {/key}
        </Route>
        <Route path="/">
            <p>Click a name on the left or enter a name in the "Add Contact" field to start a new conversation.</p>
        </Route>
    </main>
</Router>

<style>
 main {
     padding: 1em;
     display: flex;
     height: 100%;
     width: 100%;
     box-sizing: border-box;
 }
</style>
