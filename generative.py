#!/home/despoB/mb3152/anaconda/bin/python
import brain_graphs
import os
from igraph import Graph, VertexClustering
import numpy as np
import pandas as pd
from multiprocessing import Pool
from itertools import combinations
import pylab as plt
import seaborn as sns
sns.plt.rcParams['pdf.fonttype'] = 42
from multiprocessing import Pool
import glob
import scipy
from richclub import preserve_strength, RC
from multiprocessing import Pool
import sys
import pickle
import time
"""
SGE:
qdel -u mb3152
qsub -V -l mem_free=1G -pe threaded 20 -j y -o /home/despoB/mb3152/sge/ -e /home/despoB/mb3152/dynamic_mod/sge/ -N g264_1000 generative.py '264' '1000' '40'
qsub -V -l mem_free=1G -pe threaded 20 -j y -o /home/despoB/mb3152/sge/ -e /home/despoB/mb3152/dynamic_mod/sge/ -N g500_500 generative.py '500' '500' '40'
qsub -V -l mem_free=1G -pe threaded 20 -j y -o /home/despoB/mb3152/sge/ -e /home/despoB/mb3152/dynamic_mod/sge/ -N g1000_50 generative.py '1000' '50' '40'
qsub -V -l mem_free=1G -pe threaded 20 -j y -o /home/despoB/mb3152/sge/ -e /home/despoB/mb3152/dynamic_mod/sge/ -N g2500_25 generative.py '2500' '25' '40'
"""

def get_power_pc(hub='pc'):
    data = pd.read_csv('/home/despoB/mb3152/modularity/mmc3.csv')
    data['new'] = np.zeros(len(data))
    if hub == 'pc':
        for x2,y2,z2,pc in zip(data.X2,data.Y2,data.Z2,data.PC):
            data.new[data[data.X1==x2][data.Z1==z2][data.Y1==y2].index[0]] = pc
    else:
    	1/0
        for roi_num,x,y,z,ap in zip(data.index,data.X1,data.Y1,data.Z1,data.CD):
            fill_index = data.new[data.X2==x][data.Y2==y][data.Z2==z]
            data.new[fill_index.index.values[0]] = ap
    values_dict = data.new.to_dict()
    return values_dict

def calculate_node_within_community_betweeness(graph,membership,community):
	wcsp = np.zeros((graph.vcount()))
	community_nodes = np.where(membership==community)[0]
	for node1,node2 in combinations(community_nodes,2):
		shortest_path = graph.get_shortest_paths(node1,node2,weights='weight',output ='vpath')[0][1:-1]
		wcsp[shortest_path] = wcsp[shortest_path] + 1
	return wcsp

def calculate_node_between_community_betweeness(graph,nodes,membership,community):
	bcsp = np.zeros((graph.vcount()))
	for node1,node2 in combinations(nodes,2):
		if membership[node1] == membership[node2]:
			continue
		shortest_path = graph.get_shortest_paths(node1,node2,weights='weight',output ='vpath')[0][1:-1]
		bcsp[shortest_path] = bcsp[shortest_path] + 1
	bcsp[membership==community] = 0.0
	return bcsp

def generate_initial_edges(graph,node,n_edges,possible_nodes,membership,within):
	nodes = []
	for n in possible_nodes:
		if n == node:
			continue
		if graph.get_eid(node,n,error=False) != -1:
			continue
		if membership[n]!=membership[node] and within == False:
			nodes.append(n)
		if membership[n]==membership[node] and within == True:
			nodes.append(n)
	for n in nodes:
		if within == False:
			assert membership[n] != membership[node]
		else:
			assert membership[n] == membership[node]
	assert len(nodes) >= n_edges, 'Not enough nodes in community to create that many edges'
	edges = []
	while len(edges) < n_edges:
		edge = (node,np.random.choice(nodes))
		if edge[0] == edge[1]:
			continue
		if edge in edges:
			continue
		if (edge[1],edge[0]) in edges:
			continue
		edges.append(edge)
	return edges

def generate_and_add_between_edges(graph,membership,node,bcb,n_between_edges,communities_to_add_to):
	# might want to randomlly sample from real data for communities_to_add_to
	# get distribution of community strengths for the community this node is in 
	community_nodes = np.argwhere(membership==membership[node])
	communities = np.unique(membership)
	node_degree_by_community = np.zeros(len(communities))
	for comm_idx,c in enumerate(communities):
		comm_total_degree = 0.
		for node1 in community_nodes:
			for node2 in np.argwhere(np.array(membership)==c).reshape(-1):
				eid = graph.get_eid(node1,node2,error=False)
				if eid == - 1:
					continue
				comm_total_degree = comm_total_degree + 1
			node_degree_by_community[comm_idx] = comm_total_degree
	node_degree_by_community[membership[node]] = 0.0
	non_zero = len(node_degree_by_community[node_degree_by_community>0])
	if non_zero < communities_to_add_to:
		communities_to_add_to = non_zero
	node_degree_by_community = node_degree_by_community/sum(node_degree_by_community)
	print communities_to_add_to
	communities_to_add_to = np.random.choice(communities,size=communities_to_add_to,p=node_degree_by_community,replace=False)
	temp_membership = np.array(membership).copy()
	for i in enumerate(temp_membership):
		if i not in communities_to_add_to:
			temp_membership[membership==i] = -1
	sorted_bcb = np.argsort(bcb)
	sorted_bcb = np.fliplr([sorted_bcb])[0]
	nba = 0.
	while True:
		for node2 in sorted_bcb:
			if temp_membership[node2] == -1:
				continue
			if temp_membership[node] == temp_membership[node2]:
				continue
			if bcb[node2] == 0.0:
				node2 = np.random.choice(np.where(bcb==0.0)[0].reshape(-1))
			if graph.get_eid(node,node2,error=False) != -1:
				continue
			if graph.degree()[node2] == 0.0:
				continue
			graph = add_edges(graph,[[node,node2]])
			nba = nba + 1
			if nba >= n_between_edges:
				break
		if nba >= n_between_edges:
			break
	return graph

def generate_and_add_within_edges(graph,membership,node,wcb,n_within_edges):
	sorted_wcb = np.argsort(wcb)
	sorted_wcb = np.fliplr([sorted_wcb])[0]
	nwa = 0.
	trials = 0.0
	while True:
		for node2 in sorted_wcb:
			if membership[node] != membership[node2]:
				continue
			if wcb[node2] == 0.0:
				node2 = np.random.choice(np.where(wcb==0.0)[0].reshape(-1))
			if graph.get_eid(node,node2,error=False) != -1:
				continue
			if graph.degree()[node2] == 0.0:
				continue
			graph = add_edges(graph,[[node,node2]])
			nwa = nwa + 1
			if nwa >= n_within_edges:
				break
		if nwa >= n_within_edges:
			break
		if trials > len(sorted_wcb)*10:
			1/0
	return graph

def add_edges(graph,edges):
	for edge in edges:
		try:
			assert graph.get_eid(edge[0],edge[1],error=False) == -1
			graph.add_edge(edge[0],edge[1],weight=1)
		except:
			print 'Tried to add edge that already exists'
	return graph

def calculate_num_edges(density,gammas,n_nodes,n_edges):
	# number of total edges in graph at density we select.
	# this is the number of edges that should be present, given n_nodes and density.
	n_total_edges = np.ceil(((n_nodes*(n_nodes-1.))/2.)*density)
	# thus, we have to add the difference between the number present, and the number that would give us the density we want
	n_edges = n_total_edges-n_edges
	# however, we might have too many edges in the graph already, so let's just go with average
	# since we are adding a node, this should cause the density to decrese slightly.
	if n_edges < 0.0:
		n_edges = np.floor(n_total_edges/float(n_nodes+1))
	n_edges = int(n_edges)
	n_between_edges = 0
	n_within_edges = 0
	g = gammas[np.random.randint(0,len(gammas))]
	assert sum(g) > 0.0
	pr = g/sum(g)
	for n in range(n_edges):
		choice = np.random.choice([0,1],p=pr)
		if choice == 1:
			n_within_edges += 1
		else:
			n_between_edges += 1
	return n_between_edges,n_within_edges

def initial_graph(seed_nodes,n_nodes,n_communities,pi,gammas,density=.15):
	#make node array for seeds
	nodes = np.array(range(seed_nodes))
	#make membership
	membership = np.zeros(n_nodes)-1
	# make inital empty graph
	graph = Graph(directed=False)
	# add all nodes
	graph.add_vertices(range(len(membership)))
	# initialize membership
	curr_length = 0
	for i in range(n_communities):
		num_nodes = np.ceil(pi[i]*seed_nodes)
		membership[curr_length:curr_length+num_nodes] = i
		curr_length += num_nodes
	# trick calculate_num_edges
	n_edges= int(np.ceil((((seed_nodes-1)*(seed_nodes-2.))/2.)*density))
	for node in nodes:
		while True:
			try:
				# given number of nodes in intial graph, and gammas, estimate number of within and between edges for this node.
				n_between_edges, n_within_edges = calculate_num_edges(density=density,gammas=gammas,n_nodes=seed_nodes,n_edges=n_edges)
				within_edges = generate_initial_edges(graph=graph,node=node,n_edges=n_within_edges,possible_nodes=nodes,membership=membership,within=True)
				between_edges = generate_initial_edges(graph=graph,node=node,n_edges=n_between_edges,possible_nodes=nodes,membership=membership,within=False)
				graph = add_edges(graph,within_edges)
				graph = add_edges(graph,between_edges)
				break
			except:
				print 'Finding new gamma for node in initialization'
	return graph,membership

def find_edgeless_nodes(graph):
	edgeless_nodes = np.array(graph.degree())
	edged_nodes = np.where(edgeless_nodes>0)[0]
	edgeless_nodes = np.where(edgeless_nodes==0)[0]
	return edgeless_nodes,edged_nodes

def find_new_node(graph,pi,n_communities):
	found = False
	while found == False:
		edgeless_nodes,edged_nodes = find_edgeless_nodes(graph)
		node = np.random.choice(edgeless_nodes)
		try:
			assert node not in edged_nodes
			found = True
		except:
			found = False
	return node,np.random.choice(range(n_communities),p=pi)

def get_real_data(density=.2):
	gammas = []
	matrices = glob.glob('/home/despoB/mb3152/dynamic_mod/matrices/*rfMRI_REST*matrix*')
	matrix = np.load(matrices[0])
	for m in matrices[1:]:
		matrix = np.nansum([matrix,np.load(m)],axis=0)
	matrix = matrix/len(matrices)
	graph = brain_graphs.matrix_to_igraph(matrix,density,binary=False,check_tri=True,interpolation='midpoint',normalize=False)
	graph = graph.community_infomap(edge_weights='weight')
	membership = np.array(graph.membership)
	for node in range(matrix.shape[0]):
		community = membership[node]
		community_nodes = np.argwhere(membership==community)
		non_community_nodes = np.argwhere(membership!=community)
		within = np.ceil(np.sum(matrix[node,community_nodes]))
		between = np.ceil(np.sum(matrix[node,non_community_nodes]))
		if within + between == 0.0:
			continue
		gammas.append([between,within])
	graph = brain_graphs.brain_graph(graph)
	return gammas,graph.pc,graph.wmd

def get_pi(seed_nodes,n_nodes,density,gammas,equal_community_size):
	"""
	caclulate the number of within community edges that each node will have, at most (at least for a random sample 5 times the length of seed_nodes).
	this is important, as we want to make sure we can actually create a graph with the supplied parameters
	for example, if the gamma and density is too high, and communities too small, it is impossible to initialize this graph.
	"""
	n_within_edges = []
	# this is the theoretical number of edges present before we add the node.
	n_edges= int(np.ceil((((seed_nodes-1)*(seed_nodes-2.))/2.)*density))
	for n in range(int(seed_nodes*5)):
		n_within_edges.append(np.ceil(calculate_num_edges(density=density,gammas=gammas,n_nodes=seed_nodes,n_edges=n_edges)[1]))
	n_within_edges = np.max(n_within_edges)
	#make sure it will grow all the way. for this we calculate what the largest number of within community edges that might be added.
	n_within_edges_final = []
	# this is the theoretical number of edges present before we add the node.
	n_edges= int(np.ceil((((n_nodes-1)*(n_nodes-2.))/2.)*density))
	for n in range(int(seed_nodes*5)):
		n_within_edges_final.append(np.ceil(calculate_num_edges(density=density,gammas=gammas,n_nodes=n_nodes,n_edges=n_edges)[1]))
	n_within_edges_final = np.max(n_within_edges_final)
	#generate community sizes by making a distribution
	if equal_community_size:
		pi = np.ones(n_communities)/n_communities
	else:
		for i in range(10000):
			pi = np.random.dirichlet(alpha=np.ones(n_communities))
			#make sure all communities have enough nodes to satisfy gamma
			large_enough = 0
			for i in range(len(pi)):
				#calculate the size of the community, assuming it might get rounded down.
				community_size = np.floor(pi[i]*seed_nodes)
				#calculate the number of edges this community can have total
				possible_within_edges = np.floor((community_size*(community_size-1))/2.)
				#ensure that we do not have more within_community edges than possible for community
				if n_within_edges * (community_size+1) < possible_within_edges:
					large_enough += 1
				#calculate the size of the community, assuming it might get rounded down, but now for the whole graph.
				community_size = np.floor(pi[i]*n_nodes)
				#calculate the number of edges this community can have total
				possible_within_edges = np.floor((community_size*(community_size-1))/2.)
				#ensure that we do not have more within_community edges than possible for community
				if n_within_edges_final * (community_size+1) < possible_within_edges:
					large_enough += 1
			if large_enough == n_communities*2:
				break
		assert i < 9999, 'Could not satisfy parameters'
	return pi

def generative_model_shortest_paths_win(n_nodes=264,n_communities=4,gamma=.95,density=.1,intial_community_density=.1,equal_community_size=False):

	n_nodes=264
	n_communities=8
	density=.05
	intial_community_density=.1
	equal_community_size=False

	"""
	Parameters
	n_nodes: number of nodes in final iteration of the graph
	n_communities: number of communities in graph
	gamma: fraction of between and within module edges
	gamma, and its distribution should be extimated on real data. Just get a set of ratios at given density, and randomly choose from it. 
	density: fraction of edges that exists relative to complete graph
	intial_community_density: the density of nodes that are added to each community in initialization of graph
	equal_community_size: True, or False if uneven communities are wanted, for which a dirichlet distribution is used.

	Initialization

	Caclulate the number of nodes to modules, according to size, and randomly add edges to match density and gamma

	Generative Growth Model

	1. 
	Compute number of between and within module edges to add, based on density and fraction
	2. 
	within module edge
	for each node, 1 / average shortest path. to power of BETA
		add edges to nodes with most shortest paths through it.

	between module edge
	for each node not in the module, get average shortest path between nodes not in module, but consider paths through module. 
		add edges to nodes with most shortest paths through it. 
	"""
	1/0
	#intialize graph with number of nodes based on community density, total n_nodes, and n_communities.
	#this ensures that a certain percentage of nodes in each community are present in initalization of graph.
	#for example, an intial_community_density of .2 ensure that each community has twenty percent of its nodes present during initialization
	seed_nodes = np.ceil(intial_community_density *(n_nodes/n_communities))*n_communities
	gammas,pc,wmd = get_real_data(density)
	pi = get_pi(seed_nodes,n_nodes,density,gammas,equal_community_size)
	#pass pi,gammas, and parameters to make graph.
	graph,membership = initial_graph(int(seed_nodes),int(n_nodes),int(n_communities),pi,gammas,density)
	n_nodes_in_graph = len(find_edgeless_nodes(graph)[1])
	assert len(np.unique(membership[membership>=0])) == n_communities
	assert n_nodes_in_graph == seed_nodes, 'Initialization failed, different number of nodes than requested'
	print 'Graph initialized with ' + str(n_nodes_in_graph) + ' nodes and a density of: ' + str(graph.ecount()/((n_nodes_in_graph*(n_nodes_in_graph-1))/2.))
	pr = np.logspace(0,1,n_communities)**3
	pr = pr / sum(pr)
	pr = np.flipud(pr)
	"""
	you should make it so that the number of communities the node gets added to is proportional to the between edges 
	is there a correlation between sum of PC and efficiency?
	"""
	while n_nodes_in_graph < n_nodes:
		if str(n_nodes_in_graph)[-1] == '0':
			print str(n_nodes_in_graph) + str(' nodes, ') + str(graph.ecount()) + ' edges in graph and density of: ' + str(graph.ecount()/((n_nodes_in_graph*(n_nodes_in_graph-1))/2.))
		node,community = find_new_node(graph,pi,n_communities)
		membership[node] = community
		wcb = calculate_node_within_community_betweeness(graph,membership,community)
		bcb = calculate_node_between_community_betweeness(graph,np.argwhere(membership!=-1).reshape(-1),membership,community)
		communities_to_add_to = np.random.choice(range(1,n_communities+1),p=pr)
		n_between_edges, n_within_edges = calculate_num_edges(density,gammas,n_nodes_in_graph+1,graph.ecount())
		generate_and_add_between_edges(graph,membership,node,bcb,n_between_edges,communities_to_add_to)
		generate_and_add_within_edges(graph,membership,node,wcb,n_within_edges)
		print 'adding %s within community edges and %s between community edges' %(n_within_edges,n_between_edges)
		n_nodes_in_graph = len(find_edgeless_nodes(graph)[1])
	brain_graph = brain_graphs.brain_graph(VertexClustering(graph,membership=membership.astype(int)))
	return brain_graphs.brain_graph(VertexClustering(graph, membership=membership.astype(int)))

def calc_num_edges(n_nodes,density):
	return np.ceil(((n_nodes*(n_nodes-1.))/2.)*density)

def make_prs(variables):
	temp_graph=variables[0]
	edge=variables[1]
	orig_q=variables[2]
	orig_sps=variables[3]
	temp_graph.delete_edges(edge)
	if temp_graph.is_connected() == False:
		return [-10000,-10000]
	return [orig_sps-np.sum(temp_graph.shortest_paths()),temp_graph.community_fastgreedy().as_clustering().modularity-orig_q]

def preferential_routing_multi(variables):
	metric = variables[0]
	n_nodes = variables[1]
	density = variables[2]
	graph = variables[3]
	np.random.seed(variables[4])
	print variables[4],variables[0]
	# t1 = time.time()
	while True:
		delete_edges = graph.get_edgelist()
		if metric != 'none':
			vc = graph.community_fastgreedy().as_clustering()
			orig_q = vc.modularity
			membership = vc.membership
			community_matrix = brain_graphs.community_matrix(membership,0)
			community_matrix[np.isnan(community_matrix)] == 1
			orig_sps = np.sum(np.array(graph.shortest_paths())[community_matrix!=1])
			q_edge_scores = []
			sps_edges_scores = []
			for edge in delete_edges:
				eid = graph.get_eid(edge[0],edge[1],error=False)
				graph.delete_edges(eid)
				q_edge_scores.append(VertexClustering(graph,membership).modularity-orig_q)
				sps_edges_scores.append(orig_sps-np.sum(np.array(graph.shortest_paths())[community_matrix!=1]))
				graph.add_edge(edge[0],edge[1],weight=1)
			q_edge_scores = np.array(q_edge_scores)
			sps_edges_scores = np.array(sps_edges_scores)
			if len(np.unique(sps_edges_scores)) > 1:
				q_edge_scores = scipy.stats.rankdata(q_edge_scores,method='min')
				sps_edge_scores = scipy.stats.rankdata(sps_edges_scores,method='min')
				scores = q_edge_scores + sps_edges_scores
			else:
				scores = scipy.stats.rankdata(q_edge_scores,method='min')
		if metric == 'q':
			edges = np.array(delete_edges)[np.argsort(scores)][int(-(graph.ecount()*.05)):]
			edges = np.array(list(edges)[::-1])
		if metric == 'none':
			scores = np.random.randint(0,100,(int(graph.ecount()*.05))).astype(float)
			edges = np.array(delete_edges)[np.argsort(scores)]
		for edge in edges:
			eid = graph.get_eid(edge[0],edge[1],error=False)
			graph.delete_edges(eid)
			if graph.is_connected() == False:
				graph.add_edge(edge[0],edge[1],weight=1)
			if graph.density() <= density:
				break
		if graph.density() <= density:
			break
	sys.stdout.flush()
	vc = brain_graphs.brain_graph(graph.community_fastgreedy().as_clustering())
	pc = vc.pc
	pc[np.isnan(pc)] = 0.0
	pc_emperical_phis = RC(graph,scores=pc).phis()
	pc_average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=pc).phis() for i in range(25)],axis=0)
	pc_normalized_phis = pc_emperical_phis/pc_average_randomized_phis
	degree_emperical_phis = RC(graph, scores=graph.strength(weights='weight')).phis()
	average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=graph.strength(weights='weight')).phis() for i in range(25)],axis=0)
	degree_normalized_phis = degree_emperical_phis/average_randomized_phis
	# print time.time() - t1
	return [metric,pc_normalized_phis,degree_normalized_phis,graph]

def small_rich_clubs():
	n_nodes = 1000
	density = .10
	rcs = []
	d_rcs = []
	mods = []
	x = ((density/2.)*n_nodes)
	for i in range(10):
		i = i * 10
		graph=Graph.Watts_Strogatz(1,n_nodes,int(np.around(x)),i*0.01)
		graph.es["weight"] = np.ones(graph.ecount())
		vc = brain_graphs.brain_graph(graph.community_fastgreedy().as_clustering())
		pc = vc.pc
		pc[np.isnan(pc)] = 0.0
		pc_emperical_phis = RC(graph,scores=pc).phis()
		pc_average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=pc).phis() for i in range(25)],axis=0)
		pc_normalized_phis = pc_emperical_phis/pc_average_randomized_phis
		rcs.append(pc_normalized_phis[int(graph.vcount()*.8):int(graph.vcount()*.9)])
		mods.append(vc.community.modularity)
		degree_emperical_phis = RC(graph, scores=graph.strength(weights='weight')).phis()
		average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=graph.strength(weights='weight')).phis() for i in range(25)],axis=0)
		degree_normalized_phis = degree_emperical_phis/average_randomized_phis
		d_rcs.append(degree_normalized_phis[int(graph.vcount()*.8):int(graph.vcount()*.9)])

def make_graph(variables):
	n_nodes = variables[0]
	np.random.seed(variables[1])
	graph = Graph()
	graph.add_vertices(n_nodes)
	while True:
		i = np.random.randint(0,n_nodes)
		j = np.random.randint(0,n_nodes)
		if i == j:
			continue
		if graph.get_eid(i,j,error=False) == -1:
			graph.add_edge(i,j,weight=1)
		if graph.density() > .35 and graph.is_connected() == True:
			break
	# graph.es["weight"] = np.random.randint(0,100,graph.ecount())*0.1
	graph.es["weight"] = np.ones(graph.ecount())
	return graph

def make_small_world(variables):
	density = variables[1]
	n_nodes = variables[0]
	x = ((density/2.)*n_nodes)
	graph=Graph.Watts_Strogatz(1,n_nodes,int(np.around(x)),0.5)
	graph.es["weight"] = np.ones(graph.ecount())
	return graph

def preferential_routing(n_nodes=300,density=0.05,iters=100,cores=40):
	pool = Pool(cores)
	none_deg_rc = []
	none_pc_rc = []
	none_graphs = []
	both_deg_rc = []
	both_pc_rc = []
	both_graphs = []
	variables = []
	for i in range(iters):
		variables.append([n_nodes,i])
	graphs = pool.map(make_graph,variables)
	variables = []
	for i,g in enumerate(graphs):
		variables.append(['none',n_nodes,density,g.copy(),i])
	for i,g in enumerate(graphs):
		variables.append(['q',n_nodes,density,g.copy(),i])
	sys.stdout.flush()
	results = pool.map(preferential_routing_multi,variables)
	for r in results:
		if r[0] == 'none':
			none_pc_rc.append(r[1])
			none_deg_rc.append(r[2])
			none_graphs.append(r[3])
		else:
			both_pc_rc.append(r[1])
			both_deg_rc.append(r[2])
			both_graphs.append(r[3])
	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_none_%s_%s'%(iters,n_nodes),'w+') as f:
		pickle.dump(none_graphs,f)
	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_both_%s_%s'%(iters,n_nodes),'w+') as f:
		pickle.dump(both_graphs,f)
	np.save('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_pc_none_%s_%s.npy'%(iters,n_nodes),np.array(none_pc_rc))
	np.save('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_deg_none_%s_%s.npy'%(iters,n_nodes),np.array(none_deg_rc))
	np.save('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_pc_both_%s_%s.npy'%(iters,n_nodes),np.array(both_pc_rc))
	np.save('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_deg_both_%s_%s.npy'%(iters,n_nodes),np.array(both_deg_rc))

	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_none_%s_%s'%(iters,n_nodes),'r') as f:
		none_graphs = pickle.load(f)
	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_both_%s_%s'%(iters,n_nodes),'r') as f:
		both_graphs = pickle.load(f)

	none_mods = []
	for g in none_graphs:
		none_mods.append(g.community_fastgreedy().as_clustering().modularity)
	both_mods = []
	for g in both_graphs:
		both_mods.append(g.community_fastgreedy().as_clustering().modularity)
	print scipy.stats.ttest_ind(both_mods,none_mods)
	print np.mean(both_mods),np.mean(none_mods)
	none_mods = []
	for g in none_graphs:
		none_mods.append(np.sum(g.shortest_paths()))
	both_mods = []
	for g in both_graphs:
		both_mods.append(np.sum(g.shortest_paths()))
	print scipy.stats.ttest_ind(both_mods,none_mods)
	print np.mean(both_mods),np.mean(none_mods)

def known_graphs():
	iters = 100
	pc_rc = []
	deg_rc = []
	for i in range(iters):
		while True:
			# graph=Graph.Watts_Strogatz(1,1000,3,0.25)
			graph = Graph.Barabasi(1000,3,implementation="psumtree")
			graph.es["weight"] = np.ones(graph.ecount())
			if graph.is_connected() == True:
				break
		n_nodes = graph.vcount()
		vc = brain_graphs.brain_graph(graph.community_fastgreedy().as_clustering())
		pc = vc.pc
		pc[np.isnan(pc)] = 0.0
		pc_emperical_phis = RC(graph,scores=pc).phis()
		pc_average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=pc).phis() for i in range(5)],axis=0)
		pc_normalized_phis = pc_emperical_phis/pc_average_randomized_phis
		degree_emperical_phis = RC(graph, scores=graph.strength(weights='weight')).phis()
		average_randomized_phis = np.nanmean([RC(preserve_strength(graph,randomize_topology=True),scores=graph.strength(weights='weight')).phis() for i in range(5)],axis=0)
		degree_normalized_phis = degree_emperical_phis/average_randomized_phis
		pc_rc.append(np.nanmean(pc_normalized_phis[int(n_nodes*.75):int(n_nodes*.9)]))
		deg_rc.append(np.nanmean(degree_normalized_phis[int(n_nodes*.75):int(n_nodes*.9)]))
		print scipy.stats.ttest_ind(pc_rc,deg_rc)

def analyze_results():
	n_nodes = 100
	iters = 1000
	percent = .95
	deg_both = np.load('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_deg_both_%s_%s.npy'%(iters,n_nodes))
	pc_both = np.load('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_pc_both_%s_%s.npy'%(iters,n_nodes))
	none_pc = np.load('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_pc_none_%s_%s.npy'%(iters,n_nodes))
	none_deg = np.load('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_deg_none_%s_%s.npy'%(iters,n_nodes))
	print scipy.stats.ttest_ind(pc_both[:,n_nodes-(n_nodes/5)],none_pc[:,n_nodes-(n_nodes/5)])
	sns.set_style("white")
	sns.set_style("ticks")
	ax1 = sns.tsplot(pc_both[:,:int(n_nodes*percent)],color='black',condition='PC_Q',ci=95)
	ax2 = sns.tsplot(deg_both[:,:int(n_nodes*percent)],color='yellow',condition='Deg_Q',ci=95)
	ax3 = sns.tsplot(none_pc[:,:int(n_nodes*percent)],color='red',condition='PC_None',ci=95)
	ax4 = sns.tsplot(none_deg[:,:int(n_nodes*percent)],color='blue',condition='Deg_None',ci=95)
	sns.plt.legend(loc='upper left')
	sns.plt.ylabel('Normalized Rich Club Coefficeint')
	sns.plt.xlabel('Rank (Participation Coefficeint)')
	otherax = ax1.twinx()
	otherax.plot(scipy.stats.ttest_ind(pc_both[:,:int(n_nodes*percent)],none_pc[:,:int(n_nodes*percent)])[0],color='green',label='T Score')
	sns.plt.legend()
	sns.plt.xlim(0,int(n_nodes*percent))
	sns.plt.savefig('/home/despoB/mb3152/dynamic_mod/figures/%s_%s_generative.pdf'%(n_nodes,iters),dpi=1000)
	sns.plt.show()

def dd_fit():
	both_dd = []
	none_dd = []
	for g in both_graphs:
		both_dd.append(powerlaw.Fit(g.degree()).distribution_compare('power_law','exponential')[0])
	for g in none_graphs:
		none_dd.append(powerlaw.Fit(g.degree()).distribution_compare('power_law','exponential')[0])
	df = pd.DataFrame(np.array([both_dd,none_dd]).transpose(),columns=['Model','Random'])
	sns.violinplot(df,inner='quartile')
	sns.plt.title('Power Law Fit')
	sns.plt.legend()
	sns.plt.show()


def plt_dd_fit():
	n_nodes = 100
	iters = 1000

	"degree"
	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_none_%s_%s'%(iters,n_nodes),'r') as f:
		none_graphs = pickle.load(f)
	with open('/home/despoB/mb3152/dynamic_mod/results/rich_club_gen_graphs_both_%s_%s'%(iters,n_nodes),'r') as f:
		both_graphs = pickle.load(f)

	none_mods = []
	for g in none_graphs:
		none_mods.append(g.degree())
	both_mods = []
	for g in both_graphs:
		both_mods.append(g.degree())

	sns.kdeplot(np.array(none_mods).reshape(-1),shade=True,color='blue')
	sns.kdeplot(np.array(both_mods).reshape(-1),shade=True,color='yellow')

	sns.distplot(np.array(both_mods).reshape(-1),color='yellow',bins=20, kde=False, rug=True)

	sns.distplot(np.array(none_mods).reshape(-1),color='blue',bins=20, kde=False, rug=True)
	sns.plt.show()

	for g in both_graphs[:-1]:
		data = g.degree()
		fit = powerlaw.Fit(data, discrete=True)
		R, p = fit.distribution_compare('power_law', 'lognormal')
		print R, p
		R, p = fit.distribution_compare('power_law', 'exponential')
		print R, p
		fig = fit.plot_ccdf(color='y')
		fit.power_law.plot_ccdf(ax=fig, color='r', linestyle='--')
		# fit.lognormal.plot_ccdf(ax=fig, color='g', linestyle='--', label='Lognormal fit')
		fit.exponential.plot_ccdf(ax=fig, color='c', linestyle='--')

	data = both_graphs[-1].degree()
	fit = powerlaw.Fit(data, discrete=True)
	R, p = fit.distribution_compare('power_law', 'lognormal')
	print R, p
	R, p = fit.distribution_compare('power_law', 'exponential')
	print R, p
	fig = fit.plot_ccdf(label="Model",color='y')
	fit.power_law.plot_ccdf(ax=fig, color='r', linestyle='--', label='Power law fit')
	# fit.lognormal.plot_ccdf(ax=fig, color='g', linestyle='--', label='Lognormal fit')
	fit.exponential.plot_ccdf(ax=fig, color='c', linestyle='--', label='Exponential fit')

	####
	fig.set_ylabel(r"$p(X\geq x)$")
	fig.set_xlabel(r"Degree")
	handles, labels = fig.get_legend_handles_labels()
	fig.legend(handles, labels, loc=3)
	sns.plt.savefig('/home/despoB/mb3152/dynamic_mod/figures/both_%s_%s.pdf'%(n_nodes,iters), bbox_inches='tight')
	sns.plt.show()


	for g in none_graphs[:-1]:
		data = g.degree()
		fit = powerlaw.Fit(data, discrete=True)
		R, p = fit.distribution_compare('power_law', 'lognormal')
		print R, p
		R, p = fit.distribution_compare('power_law', 'exponential')
		print R, p
		fig = fit.plot_ccdf(color='y')
		fit.power_law.plot_ccdf(ax=fig, color='r', linestyle='--')
		# fit.lognormal.plot_ccdf(ax=fig, color='g', linestyle='--', label='Lognormal fit')
		fit.exponential.plot_ccdf(ax=fig, color='c', linestyle='--')

	data = none_graphs[-1].degree()
	fit = powerlaw.Fit(data, discrete=True)
	R, p = fit.distribution_compare('power_law', 'lognormal')
	print R, p
	R, p = fit.distribution_compare('power_law', 'exponential')
	print R, p
	fig = fit.plot_ccdf(label="RandomModel",color='y')
	fit.power_law.plot_ccdf(ax=fig, color='r', linestyle='--', label='Power law fit')
	# fit.lognormal.plot_ccdf(ax=fig, color='g', linestyle='--', label='Lognormal fit')
	fit.exponential.plot_ccdf(ax=fig, color='c', linestyle='--', label='Exponential fit')

	####
	fig.set_ylabel(r"$p(X\geq x)$")
	fig.set_xlabel(r"Degree")
	handles, labels = fig.get_legend_handles_labels()
	fig.legend(handles, labels, loc=3)
	sns.plt.savefig('/home/despoB/mb3152/dynamic_mod/figures/none_%s_%s.pdf'%(n_nodes,iters), bbox_inches='tight')
	sns.plt.show()



if len(sys.argv) > 1:
	preferential_routing(n_nodes=int(sys.argv[1]),iters=int(sys.argv[2]),cores=int(sys.argv[3]))

















